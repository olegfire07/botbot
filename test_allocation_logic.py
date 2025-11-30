import sys
import os
import pandas as pd

# Add project root to path
sys.path.append("/Users/oleg/Project_SKLAD")

from modern_bot.scripts.allocate_auction import run_allocation, AllocationConfig

def test_allocation():
    print("🚀 STARTING ALLOCATION TEST...")
    
    # Config with 6% limit
    cfg = AllocationConfig()
    cfg.max_department_percentage = 0.06
    cfg.fairness_penalty = 20.0
    
    print(f"Config: Max % = {cfg.max_department_percentage}, Fairness = {cfg.fairness_penalty}")

    # Real files
    sales_file = "/Users/oleg/Project_SKLAD/Табличная_часть_Продажи_распродажа_0109_311225.xlsx"
    stock_file = "/Users/oleg/Project_SKLAD/остатки на 301125.xlsx"
    auction_file = "/Users/oleg/Project_SKLAD/Реестр аукциона 15.11 Санкт-Петербург.xlsx"
    
    try:
        # Run allocation
        print("Running run_allocation...")
        from pathlib import Path
        dummy_output = Path("/tmp/test_alloc_output.xlsx")
        # run_allocation(sales_path, stock_path, auction_path, output_path=None, cfg=None)
        _, alloc_df, summary_df = run_allocation(sales_file, stock_file, auction_file, output_path=dummy_output, cfg=cfg)
        
        print("\n✅ ALLOCATION FINISHED!")
        print(f"Total allocated: {len(alloc_df)}")
        
        print("\n📊 DISTRIBUTION BY DEPARTMENT:")
        dist = alloc_df.groupby("department").size().sort_values(ascending=False)
        print(dist)
        
        print(f"\nTotal Departments Used: {len(dist)}")
        
        if len(dist) >= 15:
            print("\n✅ SUCCESS: Distributed to 15+ departments!")
        else:
            print(f"\n❌ FAILURE: Only {len(dist)} departments used. Goal is ~17.")
            
    except Exception as e:
        print(f"\n❌ ERROR during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_allocation()
