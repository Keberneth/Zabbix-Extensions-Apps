<#
Minimal cluster status -> JSON
Only includes the same info as the simple commands you listed:
1. (Get-ClusterGroup -Name "Cluster Group").OwnerNode
2. Get-Cluster | Select -Expand Name
3. Get-ClusterGroup | Select Name, State, OwnerNode
4. Get-ClusterNode | Select Name, State, NodeWeight, DynamicWeight
5. Get-ClusterQuorum
6. Get-Cluster | Select Name, WitnessType, WitnessInUse, WitnessDynamicWeight, WitnessResource
#>

param(
    [string]$OutputPath
)

function Safe { param([scriptblock]$S); try { & $S } catch { $null } }

# 1. Cluster Group owner node (just the name)
$clusterGroupOwnerNode = Safe { (Get-ClusterGroup -Name 'Cluster Group').OwnerNode.Name }

# 2 & 6. Cluster basic / witness info
$clusterObj = Safe { Get-Cluster }
$clusterName = $clusterObj.Name
$witnessInfo = if ($clusterObj) {
    [pscustomobject]@{
        Name                 = $clusterObj.Name
        WitnessType          = $clusterObj.WitnessType
        WitnessInUse         = $clusterObj.WitnessInUse
        WitnessDynamicWeight = $clusterObj.WitnessDynamicWeight
        WitnessResource      = $clusterObj.WitnessResource
    }
} else { $null }

# 3. Groups (flatten OwnerNode to just name; force State to string)
$groups = Safe {
    Get-ClusterGroup |
      Select-Object Name,
        @{Name='State';Expression={ $_.State.ToString() }},
        @{Name='OwnerNode';Expression={ $_.OwnerNode.Name }}
}

# 4. Nodes (force State to string)
$nodes = Safe {
    Get-ClusterNode | Select-Object Name,
        @{Name='State';Expression={ $_.State.ToString() }},
        NodeWeight, DynamicWeight
}

# 4. Nodes
$nodes = Safe {
    Get-ClusterNode | Select-Object Name, State, NodeWeight, DynamicWeight
}

# 5. Quorum (flatten)
$quorumRaw = Safe { Get-ClusterQuorum }
$quorum = if ($quorumRaw) {
    [pscustomobject]@{
        ClusterName    = $quorumRaw.Cluster.Name
        QuorumResource = $quorumRaw.QuorumResource.Name
    }
} else { $null }

$result = [pscustomobject]@{
    Timestamp              = (Get-Date -Format o)
    ClusterName            = $clusterName
    ClusterGroupOwnerNode  = $clusterGroupOwnerNode
    Groups                 = $groups
    Nodes                  = $nodes
    Quorum                 = $quorum
    Witness                = $witnessInfo
}

$json = $result | ConvertTo-Json -Depth 4
$json

if ($OutputPath) {
    $json | Out-File -FilePath $OutputPath -Encoding UTF8
}