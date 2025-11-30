import pandas as pd
import os

files = [
    "/Users/oleg/Project_SKLAD/Табличная_часть_Продажи_распродажа_0109_311225.xlsx",
    "/Users/oleg/Project_SKLAD/Реестр аукциона 15.11 Санкт-Петербург.xlsx",
    "/Users/oleg/Project_SKLAD/остатки на 301125.xlsx",
    "/Users/oleg/Project_SKLAD/отчет_о_реализации_невостр_имущества_0109_311225.xlsx"
]

for f in files:
    print(f"\n{'='*50}")
    print(f"ANALYZING: {os.path.basename(f)}")
    print(f"{'='*50}")
    
    try:
        # Read first few rows to get headers and sample data
        # Using openpyxl engine as default
        df = pd.read_excel(f, nrows=5)
        
        print(f"Columns: {list(df.columns)}")
        print(f"\nShape of sample: {df.shape}")
        print("\nFirst 3 rows:")
        print(df.head(3).to_string())
        
        # Specific checks based on file type
        if "остатки" in f:
            # Check for department column
            print("\n--- Checking Departments in Stock File ---")
            # Usually stock files have a specific structure, maybe skipping rows is needed
            # Let's try reading without header first to see structure if headers are complex
            df_raw = pd.read_excel(f, nrows=15, header=None)
            print("Raw first 15 rows (headerless):")
            print(df_raw.to_string())
            
        if "Продажи" in f or "реализации" in f:
             print("\n--- Checking Departments in Sales/Realization File ---")
             # Try to identify department column
             possible_dept_cols = [c for c in df.columns if "подразделение" in str(c).lower() or "склад" in str(c).lower()]
             if possible_dept_cols:
                 print(f"Found potential department columns: {possible_dept_cols}")

    except Exception as e:
        print(f"ERROR reading {f}: {e}")
