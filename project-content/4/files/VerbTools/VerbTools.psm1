function Get-ApprovedVerbs {
    <#
.SYNOPSIS
    Returns PowerShell approved verbs with optional filtering.

.DESCRIPTION
    This script loads approved PowerShell verbs from a JSON file and returns
    them as strongly typed objects using the ApprovedVerb class.

    Features:
    - Search across Verb, Alias, Action, Synonyms, Category
    - Filter by Category
    - List all available categories
    - Output objects by default
    - Optional table display with -DisplayTable

.PARAMETER Search
    A string used to search across all verb properties.

.PARAMETER Category
    Filters results to a specific verb category (Common, Data, Security, etc.)

.PARAMETER ListCategories
    Lists all unique categories found in the JSON file.

.PARAMETER DisplayTable
    Displays results in a formatted table instead of raw objects.

.EXAMPLE
    ./Get-ApprovedVerbs.ps1

.EXAMPLE
    ./Get-ApprovedVerbs.ps1 -Search "copy"

.EXAMPLE
    ./Get-ApprovedVerbs.ps1 -Category Data

.EXAMPLE
    ./Get-ApprovedVerbs.ps1 -ListCategories

.EXAMPLE
    ./Get-ApprovedVerbs.ps1 -DisplayTable
#>
    [CmdletBinding()]
    param(
        [string]$Search,
        [string]$Category,
        [switch]$ListCategories,
        [switch]$DisplayTable
    )
    <# DynamicParam {
        # Charger les catégories depuis le JSON
        $jsonPath = Join-Path $PSScriptRoot "Data/approved-verbs.json"
        $raw = Get-Content $jsonPath -Raw | ConvertFrom-Json
        $categories = $raw.Category | Sort-Object -Unique

        # Créer l'attribut ValidateSet dynamique
        $attribute = New-Object System.Management.Automation.ValidateSetAttribute($categories)

        # Créer le paramètre dynamique
        $param = New-Object System.Management.Automation.RuntimeDefinedParameter(
            "Category",
            [string],
            [System.Attribute[]]@($attribute)
        )

        # Retourner le dictionnaire des paramètres dynamiques
        $dict = New-Object System.Management.Automation.RuntimeDefinedParameterDictionary
        $dict.Add("Category", $param)
        return $dict
    } #>

    begin {
        # Récupérer la valeur du paramètre dynamique
        # $Category = $PSBoundParameters["Category"]
    
        # -------------------------------------------------------------------
        # CLASS DEFINITION
        # -------------------------------------------------------------------

        class ApprovedVerb {
            [string]$Verb
            [string]$Alias
            [string]$Action
            [string]$Synonyms
            [string]$Category

            ApprovedVerb([string]$Verb, [string]$Alias, [string]$Action, [string]$Synonyms, [string]$Category) {
                $this.Verb = $Verb
                $this.Alias = $Alias
                $this.Action = $Action
                $this.Synonyms = $Synonyms
                $this.Category = $Category
            }
        }

        $JsonPath = Join-Path $PSScriptRoot "Data/approved-verbs.json"
    }
    process {


    

        # -------------------------------------------------------------------
        # LOAD JSON DATA
        # -------------------------------------------------------------------

    

        if (-not (Test-Path $JsonPath)) {
            throw "JSON file not found: $JsonPath"
        }

        $RawData = Get-Content $JsonPath -Raw | ConvertFrom-Json

        # Convert JSON objects into class instances
        $ApprovedVerbs = foreach ($item in $RawData) {
            [ApprovedVerb]::new(
                $item.Verb,
                $item.Alias,
                $item.Action,
                $item.Synonyms,
                $item.Category
            )
        }

        # -------------------------------------------------------------------
        # LIST CATEGORIES
        # -------------------------------------------------------------------

        if ($ListCategories) {
            $ApprovedVerbs.Category |
            Sort-Object -Unique
            return
        }

        # -------------------------------------------------------------------
        # FILTER BY CATEGORY
        # -------------------------------------------------------------------

        if ($Category) {
            $CategoryLower = $Category.ToLower()

            $ApprovedVerbs = $ApprovedVerbs | Where-Object {
                $_.Category.ToLower() -eq $CategoryLower
            }

            if ($ApprovedVerbs.Count -eq 0) {
                Write-Host "No verbs found in category '$Category'"
                return
            }
        }

        # -------------------------------------------------------------------
        # SEARCH FILTER
        # -------------------------------------------------------------------

        if ($Search) {
            $SearchLower = $Search.ToLower()

            $ApprovedVerbs = $ApprovedVerbs | Where-Object {
                $_.Verb.ToLower().Contains($SearchLower) -or
                $_.Alias.ToLower().Contains($SearchLower) -or
                $_.Action.ToLower().Contains($SearchLower) -or
                $_.Synonyms.ToLower().Contains($SearchLower) -or
                $_.Category.ToLower().Contains($SearchLower)
            }

            if ($ApprovedVerbs.Count -eq 0) {
                Write-Host "No verbs found matching '$Search'"
                return
            }
        }

        # -------------------------------------------------------------------
        # OUTPUT
        # -------------------------------------------------------------------

        $ApprovedVerbs = $ApprovedVerbs | Sort-Object Verb

        if ($DisplayTable) {
            $ApprovedVerbs | Format-Table Verb, Alias, Action, Synonyms, Category -AutoSize
        }
        else {
            # Default: return objects
            $ApprovedVerbs
        }
    }
}

Register-ArgumentCompleter -CommandName Get-ApprovedVerbs -ParameterName Category -ScriptBlock {
    param($commandName, $parameterName, $wordToComplete, $commandAst, $fakeBoundParameters)
    # Charger les catégories depuis le JSON
    $jsonPath = Join-Path $PSScriptRoot "Data/approved-verbs.json"
    $raw = Get-Content $jsonPath -Raw | ConvertFrom-Json
    $categories = $raw.Category | Sort-Object -Unique

    foreach ($cat in $categories) {
        if ($cat -like "$wordToComplete*") {
            [System.Management.Automation.CompletionResult]::new(
                $cat,       # CompletionText
                $cat,       # ListItemText
                'ParameterValue',
                $cat        # ToolTip
            )
        }
    }
}
New-Alias -Name "gav" -Value "Get-ApprovedVerbs"

Export-ModuleMember -Function Get-ApprovedVerbs -Alias gav