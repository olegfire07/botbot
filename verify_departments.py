import pandas as pd
import sys
import os

# Add script directory to path to import local modules if needed, 
# but here we will just copy-paste the logic to verify it standalone or import if possible.
sys.path.append("/Users/oleg/Project_SKLAD")

def normalize_sku(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s

def load_stock(path):
    # Logic from allocate_auction.py
    # It seems it was using skiprows=10 or similar. Let's try to replicate or import.
    # Based on previous view_file, I don't see load_stock fully. 
    # I will try to read it with the parameters I saw in the file analysis.
    
    # In file analysis: Row 11 has "Подразделение" in column 2.
    # So header is likely row 11 (0-indexed -> 10 or 11).
    
    print(f"Loading stock from {path}...")
    try:
        df = pd.read_excel(path, header=11) # Row 11 is header (0-indexed 10? No, row 12 is data)
        # Let's check columns
        print(f"Columns found: {list(df.columns)}")
        
        if "Подразделение" in df.columns:
            depts = df["Подразделение"].dropna().unique()
            print(f"Found {len(depts)} unique departments in 'Подразделение' column.")
            print("First 5:", list(depts)[:5])
            return list(depts)
        else:
            print("Column 'Подразделение' not found with header=11.")
            return []
    except Exception as e:
        print(f"Error loading stock: {e}")
        return []

def load_sales_depts(path):
    print(f"\nLoading sales from {path}...")
    try:
        # Based on allocate_auction.py: header=None, skiprows=10, col 4 is department
        df = pd.read_excel(path, header=None, skiprows=10, usecols=[4]) 
        df.columns = ["department"]
        depts = df["department"].dropna().unique()
        print(f"Found {len(depts)} unique departments in Sales file.")
        print("First 5:", list(depts)[:5])
        return list(depts)
    except Exception as e:
        print(f"Error loading sales: {e}")
        return []

stock_file = "/Users/oleg/Project_SKLAD/остатки на 301125.xlsx"
sales_file = "/Users/oleg/Project_SKLAD/Табличная_часть_Продажи_распродажа_0109_311225.xlsx"

stock_depts = load_stock(stock_file)
sales_depts = load_sales_depts(sales_file)

print("\n--------------------------------------------------")
print(f"COMPARISON:")
print(f"Stock Depts: {len(stock_depts)}")
print(f"Sales Depts: {len(sales_depts)}")
print("--------------------------------------------------")

# Check intersection after simple normalization (lowercase, strip)
s_norm = set(str(d).lower().strip() for d in stock_depts)
sales_norm = set(str(d).lower().strip() for d in sales_depts)

common = s_norm.intersection(sales_norm)
print(f"Common Departments (normalized): {len(common)}")

missing_in_sales = s_norm - sales_norm
print(f"\nIn Stock but MISSING in Sales ({len(missing_in_sales)}):")
for d in list(missing_in_sales)[:10]:
    print(f" - {d}")
