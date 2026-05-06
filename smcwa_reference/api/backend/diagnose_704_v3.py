#!/usr/bin/env python3
"""
Diagnose 704 Sequence ID errors in SMC-LAMA
Shows recent 704 errors and sequence state
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'api/backend'))

from app.db.db import engine
from sqlalchemy import text

def diagnose():
    print("="*80)
    print("SMC-LAMA 704 SEQUENCE ERROR DIAGNOSTIC")
    print("="*80)
    
    with engine.connect() as conn:
        # Check recent 704 errors
        print("\n1. RECENT 704 ERRORS (Last 24 hours):")
        print("-"*80)
        query = text("""
            SELECT 
                sent_at,
                environment,
                exchange_id,
                metric_type,
                sequence_id,
                status_code,
                error_message as response_message,
                exchange_response::text
            FROM exchange_transactions
            WHERE status_code = 704
            AND sent_at > NOW() - INTERVAL '24 hours'
            ORDER BY sent_at DESC
            LIMIT 20
        """)
        errors = conn.execute(query).fetchall()
        
        if not errors:
            print("✅ No 704 errors in last 24 hours")
        else:
            for row in errors:
                print(f"\n  Time: {row[0]}")
                print(f"  Env: {row[1]} | Exchange: {row[2]} | Type: {row[3]}")
                print(f"  Sent Seq: {row[4]} | Status: {row[5]}")
                print(f"  Message: {row[6]}")
                if row[7]:
                    import json
                    try:
                        resp = json.loads(row[7])
                        if 'expectedSequenceId' in resp:
                            print(f"  Expected Seq: {resp['expectedSequenceId']}")
                    except: pass
        
        # Check current sequence state
        print("\n\n2. CURRENT SEQUENCE STATE:")
        print("-"*80)
        query = text("""
            SELECT 
                environment,
                exchange_id,
                metric_type,
                current_seq,
                last_updated
            FROM lama_sequence
            ORDER BY environment, exchange_id, metric_type
        """)
        seqs = conn.execute(query).fetchall()
        
        for row in seqs:
            exch_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(row[1], f"EX{row[1]}")
            print(f"  {row[0]:4} | {exch_name:5} | {row[2]:12} | Seq: {row[3]:6} | Updated: {row[4]}")
        
        # Check last successful submission per exchange
        print("\n\n3. LAST SUCCESSFUL (601) SUBMISSION PER EXCHANGE:")
        print("-"*80)
        query = text("""
            SELECT DISTINCT ON (environment, exchange_id, metric_type)
                environment,
                exchange_id,
                metric_type,
                sequence_id,
                sent_at,
                status_code
            FROM exchange_transactions
            WHERE status_code = 601
            ORDER BY environment, exchange_id, metric_type, sent_at DESC
        """)
        success = conn.execute(query).fetchall()
        
        for row in success:
            exch_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(row[1], f"EX{row[1]}")
            print(f"  {row[0]:4} | {exch_name:5} | {row[2]:12} | Last 601 Seq: {row[3]:6} | Time: {row[4]}")
        
        # Check for sequence gaps
        print("\n\n4. SEQUENCE MISMATCH DETECTION:")
        print("-"*80)
        query = text("""
            SELECT 
                ls.environment,
                ls.exchange_id,
                ls.metric_type,
                ls.current_seq as tracker_seq,
                MAX(et.sequence_id) FILTER (WHERE et.status_code = 601) as last_601_seq
            FROM lama_sequence ls
            LEFT JOIN exchange_transactions et 
                ON ls.environment = et.environment 
                AND ls.exchange_id = et.exchange_id 
                AND ls.metric_type = et.metric_type
            GROUP BY ls.environment, ls.exchange_id, ls.metric_type, ls.current_seq
        """)
        gaps = conn.execute(query).fetchall()
        
        has_mismatch = False
        for row in gaps:
            exch_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(row[1], f"EX{row[1]}")
            tracker = row[3]
            last_601 = row[4] if row[4] else 0
            
            if tracker != last_601:
                has_mismatch = True
                print(f"  ⚠️  {row[0]:4} | {exch_name:5} | {row[2]:12} | Tracker: {tracker} | Last 601: {last_601} | GAP: {tracker - last_601}")
        
        if not has_mismatch:
            print("  ✅ All sequences in sync with last successful submission")
        
        # Check for duplicate sequence IDs
        print("\n\n5. DUPLICATE SEQUENCE IDS (Last 100 transactions):")
        print("-"*80)
        query = text("""
            SELECT 
                environment,
                exchange_id,
                metric_type,
                sequence_id,
                COUNT(*) as count
            FROM (
                SELECT * FROM exchange_transactions 
                ORDER BY sent_at DESC LIMIT 100
            ) recent
            GROUP BY environment, exchange_id, metric_type, sequence_id
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        """)
        dupes = conn.execute(query).fetchall()
        
        if not dupes:
            print("  ✅ No duplicate sequence IDs in recent transactions")
        else:
            for row in dupes:
                exch_name = {1: "NSE", 2: "BSE", 4: "MCX", 5: "NCDEX"}.get(row[1], f"EX{row[1]}")
                print(f"  ⚠️  {row[0]:4} | {exch_name:5} | {row[2]:12} | Seq: {row[3]} | Used {row[4]} times")

if __name__ == "__main__":
    diagnose()
