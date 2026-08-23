from datetime import datetime, date
from sqlalchemy import String, Integer, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    phone: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    fee_toman: Mapped[int] = mapped_column(Integer, default=200000)
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    auto_reminder: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    xui_clients = relationship("XUIClient", back_populates="user")

class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount_toman: Mapped[int] = mapped_column(Integer)
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    user = relationship("User", back_populates="payments")

class Server(Base):
    __tablename__ = "servers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    username: Mapped[str] = mapped_column(String(180))
    password_encrypted: Mapped[str] = mapped_column(Text)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    snapshots = relationship("ServerSnapshot", back_populates="server", cascade="all, delete-orphan")
    clients = relationship("XUIClient", back_populates="server", cascade="all, delete-orphan")

class ServerSnapshot(Base):
    __tablename__ = "server_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    cpu: Mapped[float] = mapped_column(Float, default=0)
    mem_current: Mapped[int] = mapped_column(BigInteger, default=0)
    mem_total: Mapped[int] = mapped_column(BigInteger, default=0)
    disk_current: Mapped[int] = mapped_column(BigInteger, default=0)
    disk_total: Mapped[int] = mapped_column(BigInteger, default=0)
    net_up_bps: Mapped[int] = mapped_column(BigInteger, default=0)
    net_down_bps: Mapped[int] = mapped_column(BigInteger, default=0)
    net_sent_total: Mapped[int] = mapped_column(BigInteger, default=0)
    net_recv_total: Mapped[int] = mapped_column(BigInteger, default=0)
    client_up_total: Mapped[int] = mapped_column(BigInteger, default=0)
    client_down_total: Mapped[int] = mapped_column(BigInteger, default=0)
    online_count: Mapped[int] = mapped_column(Integer, default=0)
    client_count: Mapped[int] = mapped_column(Integer, default=0)
    xray_state: Mapped[str] = mapped_column(String(30), default="unknown")
    uptime: Mapped[int] = mapped_column(BigInteger, default=0)
    server = relationship("Server", back_populates="snapshots")

class XUIClient(Base):
    __tablename__ = "xui_clients"
    __table_args__ = (UniqueConstraint("server_id", "client_key", name="uq_server_client"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    inbound_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_key: Mapped[str] = mapped_column(String(220), index=True)
    email: Mapped[str] = mapped_column(String(220), index=True)
    protocol: Mapped[str] = mapped_column(String(30), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    up: Mapped[int] = mapped_column(BigInteger, default=0)
    down: Mapped[int] = mapped_column(BigInteger, default=0)
    total: Mapped[int] = mapped_column(BigInteger, default=0)
    expiry_time: Mapped[int] = mapped_column(BigInteger, default=0)
    last_online: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    server = relationship("Server", back_populates="clients")
    user = relationship("User", back_populates="xui_clients")

class AppEvent(Base):
    __tablename__ = "app_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
