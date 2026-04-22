from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MemberApplication(Base):
    __tablename__ = "member_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(128))
    telegram_first_name: Mapped[str | None] = mapped_column(String(128))
    telegram_last_name: Mapped[str | None] = mapped_column(String(128))

    full_name: Mapped[str] = mapped_column(String(255), index=True)
    birth_date: Mapped[date | None] = mapped_column(Date)
    phone: Mapped[str] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128))
    club: Mapped[str | None] = mapped_column(String(255))
    coach: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(64))

    application_type: Mapped[str] = mapped_column(String(32))
    membership_year: Mapped[int] = mapped_column(Integer, index=True)
    personal_data_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    data_accuracy_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="submitted", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    payment: Mapped["Payment"] = relationship(back_populates="application", cascade="all, delete-orphan", uselist=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("member_applications.id"), index=True)

    fee_type: Mapped[str] = mapped_column(String(32), index=True)
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    payment_date: Mapped[date | None] = mapped_column(Date)
    payer_full_name: Mapped[str] = mapped_column(String(255))
    operation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    payment_channel: Mapped[str | None] = mapped_column(String(128))

    receipt_original_name: Mapped[str] = mapped_column(String(255))
    receipt_content_type: Mapped[str] = mapped_column(String(128))
    receipt_size: Mapped[int] = mapped_column(Integer)
    receipt_path: Mapped[str] = mapped_column(String(512))
    receipt_sha256: Mapped[str] = mapped_column(String(64), index=True)

    auto_check_status: Mapped[str] = mapped_column(String(32), default="needs_review", index=True)
    auto_check_notes: Mapped[str] = mapped_column(Text, default="[]")
    admin_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    admin_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    application: Mapped[MemberApplication] = relationship(back_populates="payment")
