"""
Script to generate Brooklyn BIDs HTML table and NYC BID Overview from NYC Open Data API.
This pulls the Year_Found column and full BID names directly from the source data.
"""

import pandas as pd
import re

# Fetch NYC BIDs data from open data API
print("Downloading NYC BIDs data...")
bids_url = "https://data.cityofnewyork.us/api/views/7jdm-inj8/rows.csv?accessType=DOWNLOAD"
bids_data = pd.read_csv(bids_url)

# Rename columns for clarity globally
bids_data = bids_data.rename(columns={
    'F_ALL_BI_1': 'Borough',
    'F_ALL_BI_2': 'BID_Name',
    'F_ALL_BI_3': 'Properties',
    'F_ALL_BI_6': 'Assessment',
    'F_ALL_BI_7': 'Budget',
    'Year_Found': 'Year'
})

# Filter for Brooklyn BIDs only
brooklyn_bids = bids_data[bids_data['Borough'] == 'Brooklyn'].copy()

# Sort by number of properties descending
brooklyn_bids = brooklyn_bids.sort_values('Properties', ascending=False).reset_index(drop=True)

# Define colors for each BID (matching existing map colors)
colors = [
    '#e6194B', '#3cb44b', '#ffe119', '#4363d8', '#f58231',
    '#911eb4', '#42d4f4', '#f032e6', '#bfef45', '#fabed4',
    '#469990', '#dcbeff', '#9A6324', '#fffac8', '#800000',
    '#aaffc3', '#808000', '#ffd8b1', '#000075', '#a9a9a9',
    '#e6beff', '#aa6e28', '#808080'
]

# BIDs near Gowanus (for main table) - these are geographically close, in desired display order
gowanus_nearby_bids_ordered = [
    'DUMBO',
    'Montague Street',
    'Court-Livingston-Schermerhorn',
    'Fulton Mall Improvement Association',
    'MetroTech',
    'Atlantic Avenue',
    'Myrtle Avenue Brooklyn Partnership',
    'Fulton Area Business (FAB) Alliance',
    'Bed-Stuy Gateway',
    'North Flatbush',
    'Park Slope 5th Avenue'
]
gowanus_nearby_bids = set(gowanus_nearby_bids_ordered)  # For quick lookup

def format_currency(val):
    """Format currency values"""
    if pd.isna(val) or val == 0:
        return '—'
    if val >= 1000000:
        return f'${val/1000000:.1f}M'
    elif val >= 1000:
        return f'${val/1000:.0f}K'
    else:
        return f'${val:.0f}'

def generate_table_row(row, color, sequential_num, indent=False):
    """Generate an HTML table row for a BID

    Args:
        row: DataFrame row with BID data
        color: Color for the BID marker
        sequential_num: Sequential number (1, 2, 3...) based on position in table
        indent: Whether this is in the collapsed section (more indentation)
    """
    prefix = "            " if indent else "        "

    bid_name = row['BID_Name']
    properties = int(row['Properties']) if pd.notna(row['Properties']) and row['Properties'] > 0 else '—'
    assessment = format_currency(row['Assessment'])
    budget = format_currency(row['Budget'])
    year = int(row['Year']) if pd.notna(row['Year']) else '—'

    return f"""{prefix}<tr>
{prefix}    <td style="text-align: center; padding: 4px 3px;"><span style="color: {color}; font-size: 14px;">■</span> {sequential_num}</td>
{prefix}    <td style="padding: 4px 3px;">{bid_name}</td>
{prefix}    <td style="text-align: center; padding: 4px 3px;">{year}</td>
{prefix}    <td style="text-align: right; padding: 4px 3px;">{properties}</td>
{prefix}    <td style="text-align: right; padding: 4px 3px;">{assessment}</td>
{prefix}    <td style="text-align: right; padding: 4px 3px;">{budget}</td>
{prefix}</tr>
"""

# Generate the table HTML
print(f"\nFound {len(brooklyn_bids)} Brooklyn BIDs")
print("\nBIDs with data:")
for idx, row in brooklyn_bids.iterrows():
    print(f"  - {row['BID_Name']}: Year {row['Year']}, {row['Properties']} properties")

# Create a lookup dictionary for quick access to BID data by name
bid_lookup = brooklyn_bids.set_index('BID_Name').to_dict('index')

# Create main table rows in the specified order with sequential numbering (1, 2, 3...)
main_table_rows = []
sequential_num = 1
for bid_name in gowanus_nearby_bids_ordered:
    if bid_name in bid_lookup:
        row_data = bid_lookup[bid_name]
        row_data['BID_Name'] = bid_name  # Add name back for the function
        row = pd.Series(row_data)
        color = colors[(sequential_num - 1) % len(colors)]
        main_table_rows.append(generate_table_row(row, color, sequential_num))
        sequential_num += 1

# Get other BIDs (not near Gowanus), sorted by properties descending
other_bids = brooklyn_bids[~brooklyn_bids['BID_Name'].isin(gowanus_nearby_bids)].copy()
other_bids = other_bids.sort_values('Properties', ascending=False)

# Continue sequential numbering for other BIDs
other_table_rows = []
for idx, row in other_bids.iterrows():
    color = colors[(sequential_num - 1) % len(colors)]
    other_table_rows.append(generate_table_row(row, color, sequential_num, indent=True))
    sequential_num += 1

# Generate the complete HTML snippet for the table
table_html = """    <p style="margin: 0 0 8px 0; font-size: 9px; color: #666;"><b>BIDs Near Gowanus:</b></p>
    <table style="border-collapse: collapse; font-size: 10px; width: 100%;">
        <tr style="border-bottom: 2px solid #333; background-color: #f5f5f5;">
            <th style="text-align: center; padding: 5px 3px;">#</th>
            <th style="text-align: left; padding: 5px 3px;">BID Name</th>
            <th style="text-align: center; padding: 5px 3px;">Year</th>
            <th style="text-align: right; padding: 5px 3px;">Properties ▼</th>
            <th style="text-align: right; padding: 5px 3px;">Assessment</th>
            <th style="text-align: right; padding: 5px 3px;">Budget</th>
        </tr>

"""

table_html += "\n".join(main_table_rows)

# Add Gowanus BID (Proposed) row
table_html += """
        <tr style="background-color: #d4edda; border-top: 1px solid #28a745;">
            <td style="text-align: center; padding: 4px 3px;"><span style="color: #1e7e34; font-size: 14px; border: 2px solid #cc0000;">■</span></td>
            <td style="padding: 4px 3px; font-weight: bold; color: #1e7e34;">Gowanus BID (Proposed)</td>
            <td style="text-align: center; padding: 4px 3px;">—</td>
            <td style="text-align: right; padding: 4px 3px;">—</td>
            <td style="text-align: right; padding: 4px 3px;">—</td>
            <td style="text-align: right; padding: 4px 3px;">—</td>
        </tr>
    </table>
"""

# Add collapsible section for other BIDs
if other_table_rows:
    table_html += f"""
    <details style="margin-top: 8px;">
        <summary style="cursor: pointer; font-size: 10px; color: #666; padding: 4px 0;">Show all other Brooklyn BIDs ({len(other_table_rows)} more)...</summary>
        <table style="border-collapse: collapse; font-size: 10px; width: 100%; margin-top: 6px;">

"""
    table_html += "\n".join(other_table_rows)
    table_html += """        </table>
    </details>
"""

# Print the generated table
print("\n" + "="*60)
print("Generated HTML Table (copy this into brooklyn_bids.html):")
print("="*60)
print(table_html)

# Save to file
output_file = '../brooklyn_bids_table_snippet.html'
with open(output_file, 'w') as f:
    f.write(table_html)
print(f"\nTable HTML saved to {output_file}")

# ============================================================
# GENERATE BID OVERVIEW BY BOROUGH
# ============================================================
print("\n" + "="*60)
print("Generating NYC BIDs Overview by Borough...")
print("="*60)

# Borough colors (matching existing bid_overview.html)
borough_colors = {
    'Manhattan': '#3388ff',
    'Brooklyn': '#28a745',
    'Bronx': '#e67e22',
    'Queens': '#9b59b6',
    'Staten Island': '#1abc9c'
}

# Borough display order
borough_order = ['Manhattan', 'Brooklyn', 'Bronx', 'Queens', 'Staten Island']

# Aggregate data by borough
borough_stats = bids_data.groupby('Borough').agg({
    'BID_Name': 'count',
    'Properties': 'sum',
    'Assessment': 'sum',
    'Budget': 'sum'
}).rename(columns={'BID_Name': 'BID_Count'})

# Calculate totals
total_bids = borough_stats['BID_Count'].sum()
total_properties = borough_stats['Properties'].sum()
total_assessment = borough_stats['Assessment'].sum()
total_budget = borough_stats['Budget'].sum()

def format_currency_large(val):
    """Format currency values for larger amounts"""
    if pd.isna(val) or val == 0:
        return '—'
    if val >= 1000000:
        return f'${val/1000000:.1f}M'
    elif val >= 1000:
        return f'${val/1000:.1f}K'
    else:
        return f'${val:.0f}'

def format_number(val):
    """Format numbers with commas"""
    if pd.isna(val) or val == 0:
        return '—'
    return f'{int(val):,}'

# Generate borough rows
borough_rows = []
for i, borough in enumerate(borough_order):
    if borough in borough_stats.index:
        stats = borough_stats.loc[borough]
        color = borough_colors[borough]
        bg_style = ' style="background-color: #f9f9f9;"' if i % 2 == 1 else ''

        borough_rows.append(f"""        <tr{bg_style}>
            <td style="padding: 5px 4px;"><span style="color: {color}; font-size: 14px;">■</span></td>
            <td style="padding: 5px 4px;">{borough}</td>
            <td style="text-align: right; padding: 5px 4px; font-weight: bold;">{int(stats['BID_Count'])}</td>
            <td style="text-align: right; padding: 5px 4px;">{format_number(stats['Properties'])}</td>
            <td style="text-align: right; padding: 5px 4px;">{format_currency_large(stats['Assessment'])}</td>
            <td style="text-align: right; padding: 5px 4px;">{format_currency_large(stats['Budget'])}</td>
        </tr>
""")

# Generate the borough overview table HTML
overview_html = f"""    <h3 style="margin: 0 0 10px 0;">NYC BIDs by Borough (Ex. Proposed Gowanus BID)</h3>
    <table style="border-collapse: collapse; font-size: 11px; width: 100%;">
        <tr style="border-bottom: 2px solid #333; background-color: #f5f5f5;">
            <th style="text-align: left; padding: 6px 4px;"></th>
            <th style="text-align: left; padding: 6px 4px;">Borough</th>
            <th style="text-align: right; padding: 6px 4px;"># BIDs</th>
            <th style="text-align: right; padding: 6px 4px;">Properties</th>
            <th style="text-align: right; padding: 6px 4px;">Assessment</th>
            <th style="text-align: right; padding: 6px 4px;">Budget</th>
        </tr>

{"".join(borough_rows)}
        <tr style="border-top: 2px solid #333; background-color: #eee; font-weight: bold;">
            <td style="padding: 6px 4px;"></td>
            <td style="padding: 6px 4px;">Total</td>
            <td style="text-align: right; padding: 6px 4px;">{int(total_bids)}</td>
            <td style="text-align: right; padding: 6px 4px;">{format_number(total_properties)}</td>
            <td style="text-align: right; padding: 6px 4px;">{format_currency_large(total_assessment)}</td>
            <td style="text-align: right; padding: 6px 4px;">{format_currency_large(total_budget)}</td>
        </tr>
    </table>
    <p style="margin: 8px 0 4px 0; font-size: 9px; color: #888;">
        Source: NYC Small Business Services (via NYC Open Data API)<br>
        *Data quality notes: Some BIDs may have incomplete assessment/budget data
    </p>
"""

print(overview_html)

# Save borough overview to file
overview_output_file = '../bid_overview_table_snippet.html'
with open(overview_output_file, 'w') as f:
    f.write(overview_html)
print(f"\nBorough overview HTML saved to {overview_output_file}")

# Print summary
print("\n" + "="*60)
print("Summary of NYC BIDs by Borough (from live API data):")
print("="*60)
for borough in borough_order:
    if borough in borough_stats.index:
        stats = borough_stats.loc[borough]
        print(f"  {borough}: {int(stats['BID_Count'])} BIDs, {int(stats['Properties'])} properties, {format_currency_large(stats['Assessment'])} assessment, {format_currency_large(stats['Budget'])} budget")
