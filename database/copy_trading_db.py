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
