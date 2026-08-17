"""
Copy Trading Database Module for OpenAlgo + AC Agarwal (Symphony XTS).
Provides secure Fernet 256-bit encrypted credential storage, account configuration,
order logging, and activity audit trails for multi-account execution.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, scoped_session, sessionmaker
from sqlalchemy.pool import NullPool

from database.auth_db import fernet
from utils.logging import get_logger

logger = get_logger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///db/openalgo.db"

engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

SessionFactory = sessionmaker(bind=engine)
Session = scoped_session(SessionFactory)
Base = declarative_base()


def encrypt_val(val: Optional[str]) -> Optional[str]:
    """Encrypt a string value using Fernet cipher."""
    if not val:
        return None
    try:
        return fernet.encrypt(val.encode()).decode()
    except Exception as e:
        logger.error(f"Error encrypting value: {e}")
        return None


def decrypt_val(encrypted_val: Optional[str]) -> Optional[str]:
    """Decrypt a string value using Fernet cipher."""
    if not encrypted_val:
        return None
    try:
        return fernet.decrypt(encrypted_val.encode()).decode()
    except Exception as e:
        logger.error(f"Error decrypting value: {e}")
        return None


class CopyAccount(Base):
    """Child trading account configuration for multi-account copy trading."""

    __tablename__ = "copy_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String(100), nullable=False)
    client_code = Column(String(50), nullable=False, index=True)  # e.g., DM933
    broker = Column(String(50), default="acagarwal", nullable=False)

    # Encrypted API credentials
    api_key_encrypted = Column(Text, nullable=True)
    api_secret_encrypted = Column(Text, nullable=True)
    api_key_market_encrypted = Column(Text, nullable=True)
    api_secret_market_encrypted = Column(Text, nullable=True)
    auth_token_encrypted = Column(Text, nullable=True)
    auth_token_expiry = Column(DateTime, nullable=True)

    # Account Status
    is_active = Column(Boolean, default=True, index=True)
    is_primary = Column(Boolean, default=False)
    connection_status = Column(String(50), default="disconnected")  # connected | disconnected | error
    last_connected = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    # Sizing & Allocation Controls
    sizing_mode = Column(String(30), default="MULTIPLIER", nullable=False)  # MULTIPLIER | FIXED_LOTS | CAPITAL_RATIO
    multiplier = Column(Float, default=1.0, nullable=False)
    fixed_qty = Column(Integer, default=0, nullable=False)
    max_lot_cap = Column(Integer, default=50, nullable=False)

    # Risk Controls
    max_daily_loss = Column(Float, default=5000.0, nullable=False)
    daily_loss_triggered = Column(Boolean, default=False)

    # Telemetry Cache
    last_funds = Column(Float, default=0.0)
    last_pnl = Column(Float, default=0.0)
    last_positions = Column(Text, nullable=True)  # JSON serialized

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    orders = relationship("CopyOrder", back_populates="account", cascade="all, delete-orphan")
    strategy_mappings = relationship("ClientStrategyMapping", back_populates="account", cascade="all, delete-orphan")

    def set_api_key(self, key: str):
        self.api_key_encrypted = encrypt_val(key)

    def get_api_key(self) -> Optional[str]:
        return decrypt_val(self.api_key_encrypted)

    def set_api_secret(self, secret: str):
        self.api_secret_encrypted = encrypt_val(secret)

    def get_api_secret(self) -> Optional[str]:
        return decrypt_val(self.api_secret_encrypted)

    def set_api_key_market(self, key: str):
        self.api_key_market_encrypted = encrypt_val(key)

    def get_api_key_market(self) -> Optional[str]:
        return decrypt_val(self.api_key_market_encrypted)

    def set_api_secret_market(self, secret: str):
        self.api_secret_market_encrypted = encrypt_val(secret)

    def get_api_secret_market(self) -> Optional[str]:
        return decrypt_val(self.api_secret_market_encrypted)

    def set_auth_token(self, token: str):
        self.auth_token_encrypted = encrypt_val(token)

    def get_auth_token(self) -> Optional[str]:
        return decrypt_val(self.auth_token_encrypted)

    def to_dict(self, include_secrets: bool = False) -> Dict[str, Any]:
        """Convert account object to safe dictionary."""
        data = {
            "id": self.id,
            "account_name": self.account_name,
            "client_code": self.client_code,
            "broker": self.broker,
            "is_active": self.is_active,
            "is_primary": self.is_primary,
            "connection_status": self.connection_status,
            "last_connected": self.last_connected.isoformat() if self.last_connected else None,
            "error_message": self.error_message,
            "sizing_mode": self.sizing_mode,
            "multiplier": self.multiplier,
            "fixed_qty": self.fixed_qty,
            "max_lot_cap": self.max_lot_cap,
            "max_daily_loss": self.max_daily_loss,
            "daily_loss_triggered": self.daily_loss_triggered,
            "last_funds": self.last_funds,
            "last_pnl": self.last_pnl,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_secrets:
            data["api_key"] = self.get_api_key()
            data["api_secret"] = self.get_api_secret()
            data["api_key_market"] = self.get_api_key_market()
            data["api_secret_market"] = self.get_api_secret_market()
            data["auth_token"] = self.get_auth_token()
        return data


class CopyOrder(Base):
    """Audit log of orders placed for child accounts."""

    __tablename__ = "copy_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("copy_accounts.id"), nullable=False, index=True)
    master_order_id = Column(String(100), nullable=True, index=True)
    child_order_id = Column(String(100), nullable=True, index=True)
    strategy = Column(String(100), nullable=True)
    symbol = Column(String(100), nullable=False)
    exchange = Column(String(20), nullable=False)
    action = Column(String(10), nullable=False)  # BUY | SELL
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=True)
    pricetype = Column(String(20), default="MARKET")
    product = Column(String(20), default="MIS")
    status = Column(String(50), default="placed")  # placed | filled | rejected | error
    message = Column(Text, nullable=True)
    execution_latency_ms = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    account = relationship("CopyAccount", back_populates="orders")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "account_name": self.account.account_name if self.account else None,
            "client_code": self.account.client_code if self.account else None,
            "master_order_id": self.master_order_id,
            "child_order_id": self.child_order_id,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "action": self.action,
            "quantity": self.quantity,
            "price": self.price,
            "pricetype": self.pricetype,
            "product": self.product,
            "status": self.status,
            "message": self.message,
            "execution_latency_ms": self.execution_latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CopyActivityLog(Base):
    """Activity and event logs for copy trading operations."""

    __tablename__ = "copy_activity_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=True, index=True)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    status = Column(String(50), default="success")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class CopyStrategy(Base):
    """Trading strategy definition for multi-strategy routing."""

    __tablename__ = "copy_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_tag = Column(String(100), unique=True, nullable=False, index=True)  # e.g., CRUDE_1M_SCALP
    strategy_name = Column(String(150), nullable=False)
    segment = Column(String(30), default="MCXFO", nullable=False)  # MCXFO | NSEFO | NSECM
    timeframe = Column(String(20), default="1m", nullable=False)  # 1m | 5m | 15m | 1h | Daily
    default_symbol = Column(String(50), default="CRUDEOIL", nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    mappings = relationship("ClientStrategyMapping", back_populates="strategy", cascade="all, delete-orphan")

    def to_dict(self, include_subscribers: bool = False) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "strategy_tag": self.strategy_tag,
            "strategy_name": self.strategy_name,
            "segment": self.segment,
            "timeframe": self.timeframe,
            "default_symbol": self.default_symbol,
            "description": self.description,
            "is_active": self.is_active,
            "subscribers_count": len(self.mappings) if self.mappings else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_subscribers and self.mappings:
            data["subscribers"] = [m.to_dict() for m in self.mappings]
        return data


class ClientStrategyMapping(Base):
    """Relational mapping between child trading accounts and strategies."""

    __tablename__ = "client_strategy_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("copy_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    strategy_id = Column(Integer, ForeignKey("copy_strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    multiplier = Column(Float, default=1.0, nullable=False)
    fixed_qty = Column(Integer, default=0, nullable=False)
    max_daily_loss = Column(Float, default=5000.0, nullable=False)
    daily_pnl = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True, index=True)
    daily_loss_triggered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("CopyAccount", back_populates="strategy_mappings")
    strategy = relationship("CopyStrategy", back_populates="mappings")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "account_name": self.account.account_name if self.account else None,
            "client_code": self.account.client_code if self.account else None,
            "strategy_id": self.strategy_id,
            "strategy_tag": self.strategy.strategy_tag if self.strategy else None,
            "strategy_name": self.strategy.strategy_name if self.strategy else None,
            "multiplier": self.multiplier,
            "fixed_qty": self.fixed_qty,
            "max_daily_loss": self.max_daily_loss,
            "daily_pnl": self.daily_pnl,
            "is_active": self.is_active,
            "daily_loss_triggered": self.daily_loss_triggered,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CopyGlobalSetting(Base):
    """Global key-value settings store for copy trading."""

    __tablename__ = "copy_global_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_copy_trading_db():
    """Create all copy trading tables if they do not exist."""
    try:
        Base.metadata.create_all(engine)
        logger.info("Copy trading database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing copy trading database tables: {e}")


def add_child_account(
    account_name: str,
    client_code: str,
    api_key: str,
    api_secret: str,
    api_key_market: Optional[str] = None,
    api_secret_market: Optional[str] = None,
    broker: str = "acagarwal",
    sizing_mode: str = "MULTIPLIER",
    multiplier: float = 1.0,
    fixed_qty: int = 0,
    max_lot_cap: int = 50,
    max_daily_loss: float = 5000.0,
    is_primary: bool = False,
) -> Dict[str, Any]:
    """Add a new child trading account to the vault."""
    session = Session()
    try:
        account = CopyAccount(
            account_name=account_name.strip(),
            client_code=client_code.strip().upper(),
            broker=broker.strip().lower(),
            sizing_mode=sizing_mode,
            multiplier=float(multiplier),
            fixed_qty=int(fixed_qty),
            max_lot_cap=int(max_lot_cap),
            max_daily_loss=float(max_daily_loss),
            is_primary=bool(is_primary),
            is_active=True,
            connection_status="disconnected",
        )
        account.set_api_key(api_key.strip())
        account.set_api_secret(api_secret.strip())
        if api_key_market:
            account.set_api_key_market(api_key_market.strip())
        if api_secret_market:
            account.set_api_secret_market(api_secret_market.strip())

        session.add(account)
        session.commit()
        logger.info(f"Child account '{account_name}' ({client_code}) added successfully with ID {account.id}.")
        return {"status": "success", "message": "Account added successfully", "data": account.to_dict()}
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding child account: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def update_child_account(
    account_id: int,
    account_name: Optional[str] = None,
    client_code: Optional[str] = None,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    api_key_market: Optional[str] = None,
    api_secret_market: Optional[str] = None,
    sizing_mode: Optional[str] = None,
    multiplier: Optional[float] = None,
    fixed_qty: Optional[int] = None,
    max_lot_cap: Optional[int] = None,
    max_daily_loss: Optional[float] = None,
    is_active: Optional[bool] = None,
) -> Dict[str, Any]:
    """Update child trading account details."""
    session = Session()
    try:
        account = session.query(CopyAccount).filter_by(id=account_id).first()
        if not account:
            return {"status": "error", "message": "Account not found"}

        if account_name is not None:
            account.account_name = account_name.strip()
        if client_code is not None:
            account.client_code = client_code.strip().upper()
        if api_key:
            account.set_api_key(api_key.strip())
        if api_secret:
            account.set_api_secret(api_secret.strip())
        if api_key_market:
            account.set_api_key_market(api_key_market.strip())
        if api_secret_market:
            account.set_api_secret_market(api_secret_market.strip())
        if sizing_mode is not None:
            account.sizing_mode = sizing_mode
        if multiplier is not None:
            account.multiplier = float(multiplier)
        if fixed_qty is not None:
            account.fixed_qty = int(fixed_qty)
        if max_lot_cap is not None:
            account.max_lot_cap = int(max_lot_cap)
        if max_daily_loss is not None:
            account.max_daily_loss = float(max_daily_loss)
        if is_active is not None:
            account.is_active = bool(is_active)

        account.updated_at = datetime.utcnow()
        session.commit()
        return {"status": "success", "message": "Account updated successfully", "data": account.to_dict()}
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating child account {account_id}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def toggle_child_account(account_id: int, is_active: Optional[bool] = None) -> Dict[str, Any]:
    """Toggle active status for a child account."""
    session = Session()
    try:
        account = session.query(CopyAccount).filter_by(id=account_id).first()
        if not account:
            return {"status": "error", "message": "Account not found"}

        if is_active is not None:
            account.is_active = is_active
        else:
            account.is_active = not account.is_active

        session.commit()
        status_str = "activated" if account.is_active else "paused"
        return {"status": "success", "message": f"Account {status_str}", "is_active": account.is_active}
    except Exception as e:
        session.rollback()
        logger.error(f"Error toggling account {account_id}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def delete_child_account(account_id: int) -> Dict[str, Any]:
    """Delete a child account and its related logs."""
    session = Session()
    try:
        account = session.query(CopyAccount).filter_by(id=account_id).first()
        if not account:
            return {"status": "error", "message": "Account not found"}

        session.delete(account)
        session.commit()
        return {"status": "success", "message": "Account deleted successfully"}
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting account {account_id}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def get_all_child_accounts(active_only: bool = False, include_secrets: bool = False) -> List[Dict[str, Any]]:
    """Retrieve all child accounts."""
    session = Session()
    try:
        query = session.query(CopyAccount)
        if active_only:
            query = query.filter_by(is_active=True)
        accounts = query.order_by(CopyAccount.id.asc()).all()
        return [a.to_dict(include_secrets=include_secrets) for a in accounts]
    except Exception as e:
        logger.error(f"Error retrieving child accounts: {e}")
        return []
    finally:
        session.close()


def get_child_account(account_id: int, include_secrets: bool = False) -> Optional[Dict[str, Any]]:
    """Retrieve single child account by ID."""
    session = Session()
    try:
        account = session.query(CopyAccount).filter_by(id=account_id).first()
        if account:
            return account.to_dict(include_secrets=include_secrets)
        return None
    except Exception as e:
        logger.error(f"Error retrieving child account {account_id}: {e}")
        return None
    finally:
        session.close()


def update_account_status(
    account_id: int,
    connection_status: str,
    auth_token: Optional[str] = None,
    error_message: Optional[str] = None,
    funds: Optional[float] = None,
    pnl: Optional[float] = None,
):
    """Update connection status, token, funds, and PnL for an account."""
    session = Session()
    try:
        account = session.query(CopyAccount).filter_by(id=account_id).first()
        if account:
            account.connection_status = connection_status
            if connection_status == "connected":
                account.last_connected = datetime.utcnow()
                account.error_message = None
            if error_message:
                account.error_message = error_message
            if auth_token:
                account.set_auth_token(auth_token)
            if funds is not None:
                account.last_funds = float(funds)
            if pnl is not None:
                account.last_pnl = float(pnl)
            session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating account status {account_id}: {e}")
    finally:
        session.close()


def record_copy_order(
    account_id: int,
    symbol: str,
    exchange: str,
    action: str,
    quantity: int,
    price: Optional[float] = None,
    pricetype: str = "MARKET",
    product: str = "MIS",
    master_order_id: Optional[str] = None,
    child_order_id: Optional[str] = None,
    strategy: Optional[str] = None,
    status: str = "placed",
    message: Optional[str] = None,
    latency_ms: float = 0.0,
) -> Optional[int]:
    """Record placed copy order in database."""
    session = Session()
    try:
        order = CopyOrder(
            account_id=account_id,
            master_order_id=master_order_id,
            child_order_id=child_order_id,
            strategy=strategy,
            symbol=symbol,
            exchange=exchange,
            action=action.upper(),
            quantity=quantity,
            price=price,
            pricetype=pricetype,
            product=product,
            status=status,
            message=message,
            execution_latency_ms=latency_ms,
        )
        session.add(order)
        session.commit()
        return order.id
    except Exception as e:
        session.rollback()
        logger.error(f"Error recording copy order: {e}")
        return None
    finally:
        session.close()


def get_copy_orders(limit: int = 100, account_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Retrieve recent copy orders."""
    session = Session()
    try:
        query = session.query(CopyOrder)
        if account_id:
            query = query.filter_by(account_id=account_id)
        orders = query.order_by(CopyOrder.created_at.desc()).limit(limit).all()
        return [o.to_dict() for o in orders]
    except Exception as e:
        logger.error(f"Error getting copy orders: {e}")
        return []
    finally:
        session.close()


# =====================================================================
# Master Switch & Global Settings
# =====================================================================

def get_master_switch() -> bool:
    """Check if the global master copy trading switch is ACTIVE."""
    session = Session()
    try:
        setting = session.query(CopyGlobalSetting).filter_by(key="copy_trading_master_active").first()
        if setting:
            return setting.value.strip().lower() == "true"
        return True  # Default to active
    except Exception as e:
        logger.error(f"Error reading master switch: {e}")
        return True
    finally:
        session.close()


def set_master_switch(is_active: bool) -> bool:
    """Set the global master copy trading switch state."""
    session = Session()
    try:
        setting = session.query(CopyGlobalSetting).filter_by(key="copy_trading_master_active").first()
        if not setting:
            setting = CopyGlobalSetting(key="copy_trading_master_active", value=str(is_active).lower())
            session.add(setting)
        else:
            setting.value = str(is_active).lower()
            setting.updated_at = datetime.utcnow()
        session.commit()
        return is_active
    except Exception as e:
        session.rollback()
        logger.error(f"Error setting master switch: {e}")
        return False
    finally:
        session.close()


# =====================================================================
# Strategy Definition CRUD
# =====================================================================

def create_strategy(
    strategy_tag: str,
    strategy_name: str,
    segment: str = "MCXFO",
    timeframe: str = "1m",
    default_symbol: str = "CRUDEOIL",
    description: Optional[str] = None,
    is_active: bool = True,
) -> Dict[str, Any]:
    """Create a new copy trading strategy definition."""
    session = Session()
    try:
        clean_tag = strategy_tag.strip().upper().replace(" ", "_")
        existing = session.query(CopyStrategy).filter_by(strategy_tag=clean_tag).first()
        if existing:
            return {"status": "error", "message": f"Strategy with tag '{clean_tag}' already exists"}

        strat = CopyStrategy(
            strategy_tag=clean_tag,
            strategy_name=strategy_name.strip(),
            segment=segment.strip().upper(),
            timeframe=timeframe.strip(),
            default_symbol=default_symbol.strip().upper(),
            description=description.strip() if description else None,
            is_active=bool(is_active),
        )
        session.add(strat)
        session.commit()
        logger.info(f"Strategy '{strat.strategy_name}' [{strat.strategy_tag}] created successfully.")
        return {"status": "success", "message": "Strategy created successfully", "data": strat.to_dict()}
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating strategy: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def get_all_strategies(include_subscribers: bool = True) -> List[Dict[str, Any]]:
    """Retrieve all defined strategies with subscriber counts."""
    session = Session()
    try:
        strategies = session.query(CopyStrategy).order_by(CopyStrategy.id.asc()).all()
        results = []
        for s in strategies:
            data = s.to_dict(include_subscribers=include_subscribers)
            # Calculate aggregate strategy PnL across active mapped clients
            strat_pnl = 0.0
            if s.mappings:
                for m in s.mappings:
                    if m.account and m.account.is_active and m.is_active:
                        strat_pnl += float(m.daily_pnl or 0.0)
            data["total_strategy_pnl"] = round(strat_pnl, 2)
            results.append(data)
        return results
    except Exception as e:
        logger.error(f"Error retrieving strategies: {e}")
        return []
    finally:
        session.close()


def get_strategy_by_id(strategy_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve single strategy by ID."""
    session = Session()
    try:
        strat = session.query(CopyStrategy).filter_by(id=strategy_id).first()
        if strat:
            return strat.to_dict(include_subscribers=True)
        return None
    except Exception as e:
        logger.error(f"Error getting strategy {strategy_id}: {e}")
        return None
    finally:
        session.close()


def get_strategy_by_tag(strategy_tag: str) -> Optional[Dict[str, Any]]:
    """Retrieve single strategy by tag."""
    session = Session()
    try:
        clean_tag = strategy_tag.strip().upper().replace(" ", "_")
        strat = session.query(CopyStrategy).filter_by(strategy_tag=clean_tag).first()
        if strat:
            return strat.to_dict(include_subscribers=True)
        return None
    except Exception as e:
        logger.error(f"Error getting strategy tag {strategy_tag}: {e}")
        return None
    finally:
        session.close()


def update_strategy(
    strategy_id: int,
    strategy_name: Optional[str] = None,
    segment: Optional[str] = None,
    timeframe: Optional[str] = None,
    default_symbol: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Dict[str, Any]:
    """Update strategy metadata."""
    session = Session()
    try:
        strat = session.query(CopyStrategy).filter_by(id=strategy_id).first()
        if not strat:
            return {"status": "error", "message": "Strategy not found"}

        if strategy_name is not None:
            strat.strategy_name = strategy_name.strip()
        if segment is not None:
            strat.segment = segment.strip().upper()
        if timeframe is not None:
            strat.timeframe = timeframe.strip()
        if default_symbol is not None:
            strat.default_symbol = default_symbol.strip().upper()
        if description is not None:
            strat.description = description.strip()
        if is_active is not None:
            strat.is_active = bool(is_active)

        strat.updated_at = datetime.utcnow()
        session.commit()
        return {"status": "success", "message": "Strategy updated successfully", "data": strat.to_dict()}
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating strategy {strategy_id}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def delete_strategy(strategy_id: int) -> Dict[str, Any]:
    """Delete a strategy and all its client mappings."""
    session = Session()
    try:
        strat = session.query(CopyStrategy).filter_by(id=strategy_id).first()
        if not strat:
            return {"status": "error", "message": "Strategy not found"}

        session.delete(strat)
        session.commit()
        return {"status": "success", "message": "Strategy deleted successfully"}
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting strategy {strategy_id}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


# =====================================================================
# Client Strategy Mappings CRUD
# =====================================================================

def assign_strategy_to_account(
    account_id: int,
    strategy_id: int,
    multiplier: float = 1.0,
    fixed_qty: int = 0,
    max_daily_loss: float = 5000.0,
    is_active: bool = True,
) -> Dict[str, Any]:
    """Assign a trading account to a strategy with custom multiplier and risk limits."""
    session = Session()
    try:
        # Check existing mapping
        existing = session.query(ClientStrategyMapping).filter_by(
            account_id=account_id, strategy_id=strategy_id
        ).first()

        # Multiplier sanity bound: 0.1x to 10.0x
        safe_multiplier = max(0.1, min(10.0, float(multiplier)))

        if existing:
            existing.multiplier = safe_multiplier
            existing.fixed_qty = int(fixed_qty)
            existing.max_daily_loss = float(max_daily_loss)
            existing.is_active = bool(is_active)
            existing.updated_at = datetime.utcnow()
            session.commit()
            return {"status": "success", "message": "Mapping updated successfully", "data": existing.to_dict()}

        mapping = ClientStrategyMapping(
            account_id=account_id,
            strategy_id=strategy_id,
            multiplier=safe_multiplier,
            fixed_qty=int(fixed_qty),
            max_daily_loss=float(max_daily_loss),
            is_active=bool(is_active),
        )
        session.add(mapping)
        session.commit()
        return {"status": "success", "message": "Strategy assigned to account successfully", "data": mapping.to_dict()}
    except Exception as e:
        session.rollback()
        logger.error(f"Error assigning strategy {strategy_id} to account {account_id}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def get_account_strategies(account_id: int) -> List[Dict[str, Any]]:
    """Get all strategies assigned to a specific client account."""
    session = Session()
    try:
        mappings = session.query(ClientStrategyMapping).filter_by(account_id=account_id).all()
        return [m.to_dict() for m in mappings]
    except Exception as e:
        logger.error(f"Error getting strategies for account {account_id}: {e}")
        return []
    finally:
        session.close()


def update_client_strategy_mapping(
    mapping_id: int,
    multiplier: Optional[float] = None,
    fixed_qty: Optional[int] = None,
    max_daily_loss: Optional[float] = None,
    is_active: Optional[bool] = None,
) -> Dict[str, Any]:
    """Update mapping parameters for a client-strategy subscription."""
    session = Session()
    try:
        mapping = session.query(ClientStrategyMapping).filter_by(id=mapping_id).first()
        if not mapping:
            return {"status": "error", "message": "Mapping not found"}

        if multiplier is not None:
            mapping.multiplier = max(0.1, min(10.0, float(multiplier)))
        if fixed_qty is not None:
            mapping.fixed_qty = int(fixed_qty)
        if max_daily_loss is not None:
            mapping.max_daily_loss = float(max_daily_loss)
        if is_active is not None:
            mapping.is_active = bool(is_active)

        mapping.updated_at = datetime.utcnow()
        session.commit()
        return {"status": "success", "message": "Mapping updated", "data": mapping.to_dict()}
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating mapping {mapping_id}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def toggle_client_strategy_mapping(mapping_id: int, is_active: Optional[bool] = None) -> Dict[str, Any]:
    """Toggle active status for a specific client-strategy mapping."""
    session = Session()
    try:
        mapping = session.query(ClientStrategyMapping).filter_by(id=mapping_id).first()
        if not mapping:
            return {"status": "error", "message": "Mapping not found"}

        if is_active is not None:
            mapping.is_active = is_active
        else:
            mapping.is_active = not mapping.is_active

        session.commit()
        return {"status": "success", "message": "Status updated", "is_active": mapping.is_active}
    except Exception as e:
        session.rollback()
        logger.error(f"Error toggling mapping {mapping_id}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def delete_client_strategy_mapping(mapping_id: int) -> Dict[str, Any]:
    """Remove a strategy assignment from an account."""
    session = Session()
    try:
        mapping = session.query(ClientStrategyMapping).filter_by(id=mapping_id).first()
        if not mapping:
            return {"status": "error", "message": "Mapping not found"}

        session.delete(mapping)
        session.commit()
        return {"status": "success", "message": "Strategy assignment removed"}
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting mapping {mapping_id}: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


def get_active_subscribers_for_strategy_tag(strategy_tag: str) -> List[Dict[str, Any]]:
    """Retrieve all active accounts mapped to a specific strategy tag with their custom multipliers."""
    session = Session()
    try:
        clean_tag = strategy_tag.strip().upper().replace(" ", "_")
        strat = session.query(CopyStrategy).filter_by(strategy_tag=clean_tag, is_active=True).first()
        if not strat:
            return []

        mappings = session.query(ClientStrategyMapping).filter_by(
            strategy_id=strat.id, is_active=True, daily_loss_triggered=False
        ).all()

        subscribers = []
        for m in mappings:
            acc = m.account
            if acc and acc.is_active and not acc.daily_loss_triggered:
                acc_dict = acc.to_dict(include_secrets=True)
                acc_dict["strategy_multiplier"] = m.multiplier
                acc_dict["strategy_fixed_qty"] = m.fixed_qty
                acc_dict["strategy_max_daily_loss"] = m.max_daily_loss
                acc_dict["mapping_id"] = m.id
                subscribers.append(acc_dict)
        return subscribers
    except Exception as e:
        logger.error(f"Error getting subscribers for strategy tag '{strategy_tag}': {e}")
        return []
    finally:
        session.close()


# =====================================================================
# Pre-Market Readiness & Telemetry
# =====================================================================

def get_premarket_readiness_summary() -> Dict[str, Any]:
    """Calculate pre-market readiness indicators across all 100+ accounts."""
    session = Session()
    try:
        accounts = session.query(CopyAccount).all()
        total = len(accounts)
        ready = 0
        need_login = 0
        low_margin = 0

        for a in accounts:
            if not a.is_active:
                continue
            is_connected = a.connection_status == "connected" and a.get_auth_token() is not None
            has_funds = (a.last_funds or 0.0) >= 10000.0  # Alert if margin < 10,000

            if not is_connected:
                need_login += 1
            elif not has_funds:
                low_margin += 1
            else:
                ready += 1

        return {
            "total_accounts": total,
            "ready_count": ready,
            "need_login_count": need_login,
            "low_margin_count": low_margin,
            "master_switch_active": get_master_switch(),
        }
    except Exception as e:
        logger.error(f"Error computing premarket readiness: {e}")
        return {
            "total_accounts": 0,
            "ready_count": 0,
            "need_login_count": 0,
            "low_margin_count": 0,
            "master_switch_active": True,
        }
    finally:
        session.close()


def export_client_trade_logs_csv(account_id: int) -> str:
    """Generate CSV text of all executed orders for a specific client account."""
    session = Session()
    try:
        orders = session.query(CopyOrder).filter_by(account_id=account_id).order_by(CopyOrder.created_at.desc()).all()
        lines = ["ID,Time,Client Code,Strategy,Symbol,Exchange,Action,Quantity,Price,Order Type,Product,Status,Latency(ms),Message"]
        for o in orders:
            acc_code = o.account.client_code if o.account else ""
            time_str = o.created_at.strftime("%Y-%m-%d %H:%M:%S") if o.created_at else ""
            clean_msg = (o.message or "").replace(",", " ")
            lines.append(
                f"{o.id},{time_str},{acc_code},{o.strategy or ''},{o.symbol},{o.exchange},{o.action},{o.quantity},{o.price or 0.0},{o.pricetype},{o.product},{o.status},{o.execution_latency_ms:.1f},{clean_msg}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error generating CSV for account {account_id}: {e}")
        return "ID,Error\n0,Failed to export orders"
    finally:
        session.close()
