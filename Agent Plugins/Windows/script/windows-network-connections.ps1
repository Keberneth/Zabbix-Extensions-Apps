# windows-network-connections.ps1
# ----------------------------------------------------------------------------
# Lists open TCP ports, incoming vs. outgoing connections, excludes IPv6 & 127.0.0.1
# Outputs JSON with string fields, e.g.:
#   "port": "80"
#   "localip": "172.19.10.172"
#   "count": "2"
# ----------------------------------------------------------------------------

# 1. Collect LISTENING ports (exclude IPv6 & 127.0.0.1)
$allListening = Get-NetTCPConnection -State Listen
$allListening = $allListening | Where-Object { ($_.LocalAddress -notmatch ':') -and ($_.LocalAddress -ne '127.0.0.1') }

# Extract the unique ports
$LISTENPORTS = $allListening | Select-Object -ExpandProperty LocalPort -Unique | Sort-Object

# Build openPorts array
$openPorts = $LISTENPORTS | ForEach-Object {
    [PSCustomObject]@{ port = "$_" }
}

# 2. Collect ESTABLISHED connections, exclude IPv6 & loopback
$allEstablished = Get-NetTCPConnection -State Established
$allEstablished = $allEstablished | Where-Object {
    ($_.LocalAddress -notmatch ':') -and ($_.RemoteAddress -notmatch ':') `
    -and ($_.LocalAddress -ne '127.0.0.1') -and ($_.RemoteAddress -ne '127.0.0.1')
}

# 3. Split into incoming vs. outgoing
$incomingConns = $allEstablished | Where-Object { $LISTENPORTS -contains $_.LocalPort }
$outgoingConns = $allEstablished | Where-Object { $LISTENPORTS -notcontains $_.LocalPort }

# 4. Group "incomingconnections" by (LocalAddress, LocalPort, RemoteAddress)
$groupedIncoming = $incomingConns | Group-Object -Property LocalAddress,LocalPort,RemoteAddress
$incomingResults = foreach ($group in $groupedIncoming) {
    $sample = $group.Group[0]
    [PSCustomObject]@{
        localip   = "$($sample.LocalAddress)"
        localport = "$($sample.LocalPort)"
        remoteip  = "$($sample.RemoteAddress)"
        count     = "$($group.Count)"
    }
}

# 5. Group "outgoingconnections" by (LocalAddress, RemoteAddress, RemotePort)
$groupedOutgoing = $outgoingConns | Group-Object -Property LocalAddress,RemoteAddress,RemotePort
$outgoingResults = foreach ($group in $groupedOutgoing) {
    $sample = $group.Group[0]
    [PSCustomObject]@{
        localip    = "$($sample.LocalAddress)"
        remoteip   = "$($sample.RemoteAddress)"
        remoteport = "$($sample.RemotePort)"
        count      = "$($group.Count)"
    }
}

# 6. Generate "timestamp" (Unix ms * 1,000,000)
$timestamp = ([DateTimeOffset]::Now.ToUnixTimeMilliseconds() * 1000000).ToString()

# 7. Produce final JSON
$result = [ordered]@{
    openports           = $openPorts
    incomingconnections = $incomingResults
    outgoingconnections = $outgoingResults
    timestamp           = $timestamp
}

$result | ConvertTo-Json -Depth 4
