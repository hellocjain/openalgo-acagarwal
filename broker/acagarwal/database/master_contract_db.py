# broker/acagarwal/database/master_contract_db.py

import csv
import json
import os
import shutil
import pandas as pd
from broker.acagarwal.baseurl import MARKET_DATA_URL
from database.symbol import SymToken, db_session, engine, init_db
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger
from extensions import socketio

logger = get_logger(__name__)


def delete_symtoken_table():
    logger.info("[AC Agarwal] Deleting Symtoken Table")
    try:
        SymToken.query.delete()
        db_session.commit()
    except Exception as e:
        logger.error(f"[AC Agarwal] Error deleting symtoken table: {e}")
        db_session.rollback()


def copy_from_dataframe(df):
    logger.info(f"[AC Agarwal] Performing Bulk Insert of {len(df)} records")
    data_dict = df.to_dict(orient="records")
    try:
        db_session.bulk_insert_mappings(SymToken, data_dict)
        db_session.commit()
    except Exception as e:
        logger.error(f"[AC Agarwal] Error in bulk insert: {e}")
        db_session.rollback()


def download_csv_acagarwal_data(output_path):
    logger.info("[AC Agarwal] Downloading Master Contract CSV Files")
    exchange_segments = ["NSECM", "NSEFO", "BSECM", "BSEFO", "MCXFO"]
    headers_equity = "ExchangeSegment,ExchangeInstrumentID,InstrumentType,Name,Description,Series,NameWithSeries,InstrumentID,PriceBand.High,PriceBand.Low,FreezeQty,TickSize,LotSize,Multiplier,DisplayName,ISIN,PriceNumerator,PriceDenominator,DetailedDescription,ExtendedSurvIndicator,CautionIndicator,GSMIndicator\n"
    headers_fo = "ExchangeSegment,ExchangeInstrumentID,InstrumentType,Name,Description,Series,NameWithSeries,InstrumentID,PriceBand.High,PriceBand.Low,FreezeQty,TickSize,LotSize,Multiplier,UnderlyingInstrumentId,UnderlyingIndexName,ContractExpiration,StrikePrice,OptionType,DisplayName,PriceNumerator,PriceDenominator,DetailedDescription\n"

    client = get_httpx_client()
    headers = {"Content-Type": "application/json"}

    downloaded_files = []
    for segment in exchange_segments:
        payload = json.dumps({"exchangeSegmentList": [segment]})
        try:
            response = client.post(
                f"{MARKET_DATA_URL}/instruments/master", headers=headers, content=payload
            )
            if response.status_code != 200:
                logger.warning(f"[AC Agarwal] Failed to download segment {segment}. Status: {response.status_code}")
                continue

            data = response.json()
            if "result" not in data or not data["result"]:
                logger.warning(f"[AC Agarwal] Missing result field for segment {segment}")
                continue

            header = headers_equity if segment in ["NSECM", "BSECM"] else headers_fo
            segment_output_path = f"{output_path}/{segment}.csv"
            os.makedirs(output_path, exist_ok=True)

            csv_data = data["result"].split("\n")
            csv_data = [row.split("|") for row in csv_data if row.strip()]

            with open(segment_output_path, "w", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header.strip().split(","))
                writer.writerows(csv_data)
            downloaded_files.append(segment_output_path)
            logger.info(f"[AC Agarwal] Downloaded {segment}.csv ({len(csv_data)} instruments)")
        except Exception as e:
            logger.error(f"[AC Agarwal] Error downloading {segment}: {e}")

    return downloaded_files


def fetch_index_list():
    logger.info("[AC Agarwal] Fetching Index List")
    exchange_segments = [1, 11]  # NSE and BSE indexes
    headers = {"Content-Type": "application/json"}

    client = get_httpx_client()
    index_data = []

    for segment in exchange_segments:
        url = f"{MARKET_DATA_URL}/instruments/indexlist?exchangeSegment={segment}"
        try:
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                continue

            data = response.json()
            if "result" not in data or "indexList" not in data["result"]:
                continue

            for index_entry in data["result"]["indexList"]:
                if "_" in index_entry:
                    symbol_name, token = index_entry.rsplit("_", 1)
                    index_data.append(
                        {
                            "brsymbol": index_entry,
                            "symbol": symbol_name,
                            "name": symbol_name,
                            "exchange": "NSE_INDEX" if segment == 1 else "BSE_INDEX",
                            "brexchange": str(segment),
                            "token": token,
                            "expiry": "",
                            "strike": 1.0,
                            "lotsize": 1,
                            "instrumenttype": "INDEX",
                            "tick_size": 0.05,
                        }
                    )
        except Exception as e:
            logger.warning(f"[AC Agarwal] Failed index list fetch for segment {segment}: {e}")

    return index_data


def process_acagarwal_nse_csv(path):
    file_path = f"{path}/NSECM.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path, low_memory=False)
    df = df[df["Series"].isin(["EQ"])]

    token_df = pd.DataFrame()
    token_df["symbol"] = df["Name"]
    token_df["brsymbol"] = df["DisplayName"]
    token_df["name"] = df["Name"]
    token_df["exchange"] = "NSE"
    token_df["brexchange"] = "NSECM"
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = ""
    token_df["strike"] = 1.0
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = df["Series"]
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.05).astype(float)

    return token_df


def process_acagarwal_nfo_csv(path):
    file_path = f"{path}/NSEFO.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path, low_memory=False)

    token_df = pd.DataFrame()
    token_df["symbol"] = df["Description"]
    token_df["brsymbol"] = df["Description"]
    token_df["name"] = df["Name"]
    token_df["exchange"] = "NFO"
    token_df["brexchange"] = "NSEFO"
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = df["ContractExpiration"]
    token_df["strike"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(1.0)
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = df["Series"]
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.05).astype(float)

    return token_df


def process_acagarwal_mcx_csv(path):
    file_path = f"{path}/MCXFO.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path, low_memory=False)

    token_df = pd.DataFrame()
    token_df["symbol"] = df["Description"]
    token_df["brsymbol"] = df["Description"]
    token_df["name"] = df["Name"]
    token_df["exchange"] = "MCX"
    token_df["brexchange"] = "MCXFO"
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = df["ContractExpiration"]
    token_df["strike"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(1.0)
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = df["Series"]
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.05).astype(float)

    return token_df


def process_acagarwal_bse_csv(path):
    file_path = f"{path}/BSECM.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path, low_memory=False)

    token_df = pd.DataFrame()
    token_df["symbol"] = df["Name"]
    token_df["brsymbol"] = df["DisplayName"]
    token_df["name"] = df["Name"]
    token_df["exchange"] = "BSE"
    token_df["brexchange"] = "BSECM"
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = ""
    token_df["strike"] = 1.0
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = df["Series"]
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.05).astype(float)

    return token_df


def process_acagarwal_bfo_csv(path):
    file_path = f"{path}/BSEFO.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path, low_memory=False)

    token_df = pd.DataFrame()
    token_df["symbol"] = df["Description"]
    token_df["brsymbol"] = df["Description"]
    token_df["name"] = df["Name"]
    token_df["exchange"] = "BFO"
    token_df["brexchange"] = "BSEFO"
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = df["ContractExpiration"]
    token_df["strike"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(1.0)
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = df["Series"]
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.05).astype(float)

    return token_df


def master_contract_download():
    try:
        init_db()
        temp_dir = "tmp/acagarwal"
        download_csv_acagarwal_data(temp_dir)

        dfs = []
        for proc in [
            process_acagarwal_nse_csv,
            process_acagarwal_nfo_csv,
            process_acagarwal_mcx_csv,
            process_acagarwal_bse_csv,
            process_acagarwal_bfo_csv,
        ]:
            sub_df = proc(temp_dir)
            if not sub_df.empty:
                dfs.append(sub_df)

        index_list = fetch_index_list()
        if index_list:
            index_df = pd.DataFrame(index_list)
            dfs.append(index_df)

        if dfs:
            combined_df = pd.concat(dfs, ignore_index=True)
            combined_df = combined_df.dropna(subset=["symbol", "token"])
            combined_df["symbol"] = combined_df["symbol"].astype(str)
            combined_df["brsymbol"] = combined_df["brsymbol"].fillna("").astype(str)
            combined_df["name"] = combined_df["name"].fillna("").astype(str)
            combined_df["expiry"] = combined_df["expiry"].fillna("").astype(str)
            combined_df["instrumenttype"] = combined_df["instrumenttype"].fillna("").astype(str)
            delete_symtoken_table()
            copy_from_dataframe(combined_df)
            logger.info(f"[AC Agarwal] Master contract download and import complete: {len(combined_df)} records")

            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

            try:
                socketio.emit("master_contract_status", {"status": "success", "broker": "acagarwal"})
            except Exception:
                pass
            return True
        else:
            logger.error("[AC Agarwal] No records downloaded during master contract download")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return False
    except Exception as e:
        logger.error(f"[AC Agarwal] Error in master_contract_download: {e}")
        try:
            socketio.emit("master_contract_status", {"status": "error", "message": str(e), "broker": "acagarwal"})
        except Exception:
            pass
        return False
