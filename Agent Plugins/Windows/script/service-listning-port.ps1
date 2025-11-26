#–– 0) KONFIGURATION ––
# Processer du aldrig vill se:
$excludedProcesses = @(
    'Idle','System','lsass','csrss','smss','wininit','services','winlogon','svchost'
)

# Manuellt port → tjänst-/beskrivnings-map
# Port mappings per Microsoft Learn :contentReference[oaicite:0]{index=0}
$manualPortMap = @{
    # IIS / HTTP.sys
    80    = @{ ServiceName='W3SVC';        DisplayName='World Wide Web Publishing Service'; Description='HTTP (IIS)' }
    443   = @{ ServiceName='W3SVC';        DisplayName='World Wide Web Publishing Service'; Description='HTTPS (IIS)' }

    # WinRM (Remote PowerShell)
    5985  = @{ ServiceName='WinRM';        DisplayName='Windows Remote Management (WS-Management)'; Description='WinRM (HTTP)' }
    5986  = @{ ServiceName='WinRM';        DisplayName='Windows Remote Management (WS-Management)'; Description='WinRM (HTTPS)' }

    # WSUS
    8530  = @{ ServiceName='WsusService';  DisplayName='Windows Server Update Services';         Description='WSUS (HTTP)' }
    8531  = @{ ServiceName='WsusService';  DisplayName='Windows Server Update Services';         Description='WSUS (HTTPS)' }

    # SQL Server
    1433  = @{ ServiceName='MSSQLSERVER';  DisplayName='SQL Server (MSSQLSERVER)';             Description='SQL Server default instance' }

    # Active Directory Domain Services (AD DS)
    389   = @{ ServiceName='NTDS';         DisplayName='Active Directory Domain Services';     Description='LDAP' }
    636   = @{ ServiceName='NTDS';         DisplayName='Active Directory Domain Services';     Description='LDAPS (SSL)' }
    3268  = @{ ServiceName='NTDS';         DisplayName='Active Directory Domain Services';     Description='Global Catalog (unencrypted)' }
    3269  = @{ ServiceName='NTDS';         DisplayName='Active Directory Domain Services';     Description='Global Catalog (SSL)' }
    88    = @{ ServiceName='NTDS';         DisplayName='Active Directory Domain Services';     Description='Kerberos KDC' }
    135   = @{ ServiceName='RpcSs';        DisplayName='Remote Procedure Call (RPC)';          Description='RPC Endpoint Mapper' }

    # SMB / NetBIOS / File & Print
    445   = @{ ServiceName='LanmanServer'; DisplayName='Server';                                 Description='SMB/CIFS' }
    137   = @{ ServiceName='LanmanServer'; DisplayName='Server';                                 Description='NetBIOS Name Service' }
    138   = @{ ServiceName='LanmanServer'; DisplayName='Server';                                 Description='NetBIOS Datagram Service' }
    139   = @{ ServiceName='LanmanServer'; DisplayName='Server';                                 Description='NetBIOS Session Service' }

    # DNS
    53    = @{ ServiceName='DNS';          DisplayName='DNS Server';                            Description='DNS' }

    # DHCP
    67    = @{ ServiceName='DHCPServer';   DisplayName='DHCP Server';                          Description='DHCP (UDP 67)' }

    # RDS
    3389  = @{ ServiceName='TermService';  DisplayName='Remote Desktop Services';              Description='RDP' }
}

#–– 1) Hämta alla lyssnande TCP-portar ––
$ports = netstat -ano |
    ForEach-Object {
        if ($_ -match '^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)$') {
            [PSCustomObject]@{ Port=[int]$matches[1]; PID=[int]$matches[2] }
        }
    } |
    Where-Object { $_ -ne $null }

#–– 2) Bygg "vanliga" poster för allt utom våra excludedProcesses ––
$autoResults = foreach ($p in $ports) {
    $proc = Get-Process -Id $p.PID -ErrorAction SilentlyContinue
    if ($proc -and ($excludedProcesses -notcontains $proc.ProcessName)) {
        [PSCustomObject]@{
            Port        = $p.Port
            PID         = $p.PID
            Process     = $proc.ProcessName
            ServiceName = (Get-CimInstance Win32_Service -Filter "ProcessId=$($p.PID)" |
                           Select-Object -Expand Name) -or ''
            Description = try { $proc.MainModule.FileDescription } catch { 'N/A' }
        }
    }
}

#–– 3) Bygg manuella poster för Microsoft-tjänster ––
$manualResults = foreach ($p in $ports) {
    if ($manualPortMap.ContainsKey($p.Port)) {
        $map = $manualPortMap[$p.Port]
        [PSCustomObject]@{
            Port        = $p.Port
            PID         = $p.PID
            Process     = if ($p.PID -eq 4) { 'HTTP.sys (kernel)' } else {
                              (Get-Process -Id $p.PID -ErrorAction SilentlyContinue).ProcessName
                          }
            ServiceName = $map.ServiceName
            Description = $map.Description
        }
    }
}

#–– 4) Kombinera, sortera unikt och skriv ut JSON ––
$all = $autoResults + $manualResults
$all = $all | Sort-Object -Property Port,PID,Process -Unique
$all | ConvertTo-Json -Depth 3
