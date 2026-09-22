import re
from typing import Self
from urllib.parse import quote

from pydantic import BaseModel, Field, model_validator

from app.models import PHONE_PLATFORMS, ContactPlatform, SocialLink
from app.models.contact import VALUE_MAX_LENGTH

# E.164: a plus, a country code that does not start with zero, at most fifteen digits overall
E164 = re.compile(r"^\+[1-9]\d{7,14}$")

# what a seller is likely to paste instead of a bare handle
HOSTS = {
    ContactPlatform.TELEGRAM: ("t.me", "telegram.me"),
    ContactPlatform.INSTAGRAM: ("instagram.com",),
    ContactPlatform.FACEBOOK: ("facebook.com", "fb.com"),
}

HANDLE = {
    ContactPlatform.TELEGRAM: re.compile(r"^[A-Za-z0-9_]{5,32}$"),
    ContactPlatform.INSTAGRAM: re.compile(r"^[A-Za-z0-9._]{1,30}$"),
    ContactPlatform.FACEBOOK: re.compile(r"^[A-Za-z0-9.]{5,50}$"),
}

# the address template per platform; the two that reshape the value are handled apart
HREF = {
    ContactPlatform.PHONE: "tel:{value}",
    ContactPlatform.TELEGRAM: "https://t.me/{value}",
    ContactPlatform.INSTAGRAM: "https://instagram.com/{value}",
    ContactPlatform.FACEBOOK: "https://facebook.com/{value}",
}

PLATFORM_LABEL = {
    ContactPlatform.PHONE: "Телефон",
    ContactPlatform.WHATSAPP: "WhatsApp",
    ContactPlatform.TELEGRAM: "Telegram",
    ContactPlatform.VIBER: "Viber",
    ContactPlatform.INSTAGRAM: "Instagram",
    ContactPlatform.FACEBOOK: "Facebook",
}

_PHONE_NOISE = re.compile(r"[\s() -]")


def _normalize_phone(value: str) -> str:
    digits = _PHONE_NOISE.sub("", value)
    # the international prefix as it is dialled from a landline; E.164 writes it as a plus
    return f"+{digits[2:]}" if digits.startswith("00") else digits


def _normalize_handle(platform: ContactPlatform, value: str) -> str:
    """A seller pastes what the app gave them — a full profile link as often as a handle."""
    handle = value.strip().split("?")[0]
    for prefix in ("https://", "http://", "www."):
        handle = handle.removeprefix(prefix)
    for host in HOSTS[platform]:
        if handle.lower().startswith(f"{host}/"):
            handle = handle[len(host) + 1 :]
            break
    return handle.strip("/").removeprefix("@")


def href_of(platform: ContactPlatform, value: str) -> str:
    """The address is built here and never stored: a row cannot send a buyer off-platform."""
    if platform is ContactPlatform.WHATSAPP:
        # wa.me takes the number without the plus
        return f"https://wa.me/{value.removeprefix('+')}"
    if platform is ContactPlatform.VIBER:
        return f"viber://chat?number={quote(value)}"
    return HREF[platform].format(value=value)


class ContactWrite(BaseModel):
    platform: ContactPlatform
    value: str = Field(max_length=VALUE_MAX_LENGTH)

    @model_validator(mode="after")
    def _normalize_and_check(self) -> Self:
        label = PLATFORM_LABEL[self.platform]
        if self.platform in PHONE_PLATFORMS:
            self.value = _normalize_phone(self.value)
            if not E164.match(self.value):
                raise ValueError(
                    f"{label}: номер нужен в международном формате, например +37410123456"
                )
            return self

        self.value = _normalize_handle(self.platform, self.value)
        if not HANDLE[self.platform].match(self.value):
            raise ValueError(f"{label}: укажите имя профиля или ссылку на него")
        return self


class ContactsRequest(BaseModel):
    """The whole set at once: the settings screen is one form, and replacing it wholesale
    means a contact the seller cleared is gone rather than left behind by a missed delete."""

    items: list[ContactWrite] = Field(default_factory=list, max_length=len(ContactPlatform))

    @model_validator(mode="after")
    def _one_per_platform(self) -> Self:
        platforms = [item.platform for item in self.items]
        duplicate = next(
            (p for p in platforms if platforms.count(p) > 1),
            None,
        )
        if duplicate is not None:
            raise ValueError(f"{PLATFORM_LABEL[duplicate]}: можно указать только один раз")
        return self


class ContactRead(BaseModel):
    platform: ContactPlatform
    value: str
    # built from the value, so the frontend renders a link without knowing the platform rules
    href: str

    @classmethod
    def from_link(cls, link: SocialLink) -> "ContactRead":
        return cls(
            platform=link.platform, value=link.value, href=href_of(link.platform, link.value)
        )


class ContactsResponse(BaseModel):
    items: list[ContactRead]

    @classmethod
    def of(cls, links: list[SocialLink]) -> "ContactsResponse":
        return cls(items=[ContactRead.from_link(link) for link in links])
