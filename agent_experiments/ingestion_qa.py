from arango import ArangoClient, ServerVersionError, DocumentUpdateError
from datetime import datetime, timedelta
from ollama import Client
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import Lock
from tqdm.notebook import tqdm
from mlflow.genai import scorer
from mlflow.genai.scorers import Correctness, Guidelines

import getpass
import traceback
import json
import os
import random
import threading
import mlflow

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


QUESTIONS = {
        'use_case': [
            "What does your team do?",
            "What artifacts does your team produce?",
            "What do you want to achieve by using this graph application?",
        ],
        'lvl1_knowledge': [
            "What do you want to learn about this data?",
            "Do you know who created this data?",
            "How often does this data change?",
            "Who is the audience for the information gained in this application? (e.g., weekly commander brief, developer sprint planning, etc.)"
        ],
        'lvl2_knowledge': [
            "Describe to the best of your knowledge what each type of data artifact is/what it is used for.",
            "Tell me about your team's composition and skills. (e.g., 4 junior developers and 1 senior developer with skills in python and front-end development)",
           "What problem(s) is your team assigned to address?",
            "Are there naming conventions, acronyms, or jargon your team uses? If so, define them.",
            "What tools or systems touch or generate this data?"
        ],
        'lvl3_knowledge': [
            "Tell me anything you know about the structure of the data.",
            "Are there any specific pieces of information or data fields you would like identified in your data?"
        ]
    }
GEMMA3_27B_MODEL = 'gemma3:27b-it-qat'
GEMMA3_12B_MODEL = 'gemma3:12b-it-qat'
LLAMA3_3_70B_MODEL = 'llama3.3:70b'
#LLAMA3_3_70B_CUST_V1_MODEL = 'llama3.3:70b-it-q4km-cust-v1'
MAGISTRAL_24B_MODEL = 'magistral:24b'
CODELLAMA_70B_MODEL = 'codellama:70b'
DEEPSEEK_R1_70B_MODEL = 'deepseek-r1:70b'
GPT_OSS_120B_MODEL = 'gpt-oss:120b'

def get_timestamp(str_format: str = "%Y-%m-%d %H:%M:%S", no_space: bool = False):
    return datetime.now().strftime(str_format).replace(' ','__') if no_space else datetime.now().strftime(str_format)

def connect_to_arango_client(host: str):
    try:
        client = ArangoClient(hosts=host)
    except:
        print(f'{get_timestamp()} -- Could not connect to ArangoDB client at "{host}"')
        return None
    
    return client


def connect_to_arango_db(client: ArangoClient, db_name: str, username: str, password: str, max_retries: int = 3): 
    retries = 0
    if password is None:
        password = getpass.getpass(f'Please enter the password for user {username} for access to the {db_name} database: ')
        
    while retries < max_retries:
        try:
            db = client.db(db_name, username=username, password=password)     
            vers = db.version()
            print(f'{get_timestamp()} -- Successfully connected to database {db_name} running version {vers}.')
            return db
        except (ConnectionAbortedError, ServerVersionError) as e:
            retries += 1
            print(f'{get_timestamp()} -- Connection refused for db {db_name}.')
            password = getpass.getpass(f'Input password to try again:  ')
        except Exception as e:
            print(f'\n**** {type(e)}: {e} ****\n')
            retries += 1
            print(f'{get_timestamp()} -- Could not connect to db "{db_name}".')
    
    return None

def exec_aql_query(aql, query):
    cursor = aql.execute(query)
    return cursor

def append_json_to_file(new_entry, file_path, write_lock=None):
    if write_lock is not None:
        with write_lock:
            with open(file_path, 'a') as file:
                file.write(json.dumps(new_entry, default=str) + '\n')
    else:
        with open(file_path, 'a') as file:
            file.write(json.dumps(new_entry, default=str) + '\n')

def prompt_and_response(client, model, prompt, sys_set=None, quiet=False, temperature=0.8, options={}, stream=True):
    p_start = datetime.now()
    if 'temperature' not in options:
        options['temperature'] = temperature
    response = ''
    try:
        for part in client.generate(model=model, prompt=prompt, stream=stream, options=options):
            response += part['response']
            if not quiet:
                print(part['response'], end='', flush=True)
    except Exception as e:
        print(f'ERROR: {e}\nSkipping prompt...')
        traceback.format_exc(e)
        return None
    p_end = datetime.now() - p_start
    if not quiet:
        print(f'Prompt took {p_end}')

    return response

def query_user(oll_client, model, temp, json_output_file, max_followups=10, quiet=True, options={}):
    # Currently querying the user prior to reading any files only; later should include follow up questions based on artifact content
    run_params = {
        'model': model,
        'temp': temp,
        'quiet': quiet,
        'json_output_file': json_output_file
    }

    answers = {}
    mlflow.set_experiment('Model Runs')
    with mlflow.start_run(run_name=f'Ingestion-{model}-{temp}__{datetime.now()}'): 
        mlflow.log_params(run_params)

        input(f"\nThe agent will ask a series of questions to learn about your data. It will also ask up to {max_followups} follow-up questions. Answer to the best of your ability; if you do not know the answer, just say 'I don't know'. Press ENTER to begin... ")
        for qtype, qlist in QUESTIONS.items():
            for question in qlist:
                answer = input(f'\n{question}  |  ')
                # TODO: if answer is idk, we want to not continue to the next question type
                if qtype in answers:
                    answers[qtype].append({question: answer})
                else:
                    answers[qtype] = [{question: answer}]
        #print(answers)

        print("\n\nThank you! I'm generating follow-up questions now, please give me one moment...\n")
        followups_asked = 0
        agent_is_done = False
        while followups_asked < max_followups and not agent_is_done:
            prompt = f"""You are part of a team of agents ingesting data into a graph database. Your role is to ask questions to learn as much about the data as possible before another agent creates data fields for collecting metadata about each artifact. 
            
            Given the following questions and answers, determine which question needs additional information the most and ask a follow-up to that question. Respond with only the question, or "COMPLETE" if you have no more follow up questions.
            ### Questions and answers:
            {answers}
            """

            response = prompt_and_response(oll_client, model, prompt, quiet=quiet, options=options)
            if response == 'COMPLETE':
                agent_is_done = True
            else:
                answer = input(f'\n{response}  |  ')
                if 'follow_ups' in answers:
                    answers['follow_ups'].append({response: answer})
                else:
                    answers['follow_ups'] = [{response: answer}]
                followups_asked += 1
        
        if agent_is_done:
            print("\nOkay that's all the info I need, thank you!")
        else:
            print("\nOkay that's all the questions I'm allowed to ask. Thank you!")
        append_json_to_file(answers, json_output_file)
        
        #mlflow.log_metrics(
    return answers

def main():
    ar_host = 'http://localhost:8529'
    db_name = 'DB_318'
    username = 'root'
    graph_name = '318_Processes'
    
    oll_host = 'http://10.10.80.99:4001'
    mlflow.set_tracking_uri('http://localhost:5000')
    model = LLAMA3_3_70B_MODEL # GPT_OSS_120B_MODEL

    password = getpass.getpass(f'Please enter the password for user {username} for access to the {db_name} database: ')
    
    ar_client = connect_to_arango_client(ar_host)
    db = connect_to_arango_db(ar_client, db_name, username, password)
    aql = db.aql
    oll_client = Client(host=oll_host)
    
    query_user(oll_client, model, 0.3, f'./ingestion_questions__{get_timestamp(no_space=True)}.json', max_followups=5)

    
if __name__=="__main__":
    main()
    
    