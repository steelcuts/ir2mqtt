from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class IRDevice(Base):
    __tablename__ = "ir_devices"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    icon = Column(String, default="remote-tv")
    target_bridges = Column(JSON, default=[])
    allowed_bridges = Column(JSON, default=[])
    buttons = relationship("IRButton", back_populates="device", cascade="all, delete-orphan", order_by="IRButton.ordering")
    ordering = Column(Integer, default=0)


class IRButton(Base):
    __tablename__ = "ir_buttons"
    id = Column(String, primary_key=True)
    device_id = Column(String, ForeignKey("ir_devices.id"), nullable=False)
    name = Column(String, nullable=False)
    icon = Column(String, default="remote")
    is_output = Column(Boolean, default=True)
    is_input = Column(Boolean, default=False)
    is_event = Column(Boolean, default=True)
    input_mode = Column(String, default="momentary")
    input_off_delay_s = Column(Integer, default=1)
    code = relationship("IRCode", uselist=False, back_populates="button", cascade="all, delete-orphan")
    device = relationship("IRDevice", back_populates="buttons")
    ordering = Column(Integer, default=0)


class IRCode(Base):
    __tablename__ = "ir_codes"
    id = Column(Integer, primary_key=True)
    button_id = Column(String, ForeignKey("ir_buttons.id"), nullable=False)
    protocol = Column(String)
    payload = Column(JSON, default=dict)
    raw_tolerance = Column(Integer, default=20)
    button = relationship("IRButton", back_populates="code")


class IRAutomation(Base):
    __tablename__ = "ir_automations"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    enabled = Column(Boolean, default=True)
    allow_parallel = Column(Boolean, default=False)
    ha_expose_button = Column(Boolean, default=False)
    triggers = Column(JSON, default=[])
    actions = Column(JSON, default=[])
    ordering = Column(Integer, default=0)


class IrDbRemote(Base):
    __tablename__ = "irdb_remotes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False, index=True)
    path = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False, index=True)
    source_file = Column(String)
    buttons = relationship("IrDbButton", back_populates="remote", cascade="all, delete-orphan")


class IrDbButton(Base):
    __tablename__ = "irdb_buttons"
    id = Column(Integer, primary_key=True, autoincrement=True)
    remote_id = Column(Integer, ForeignKey("irdb_remotes.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    icon = Column(String)
    protocol = Column(String)
    payload = Column(JSON, default=dict)
    remote = relationship("IrDbRemote", back_populates="buttons")
