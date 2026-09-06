"""Contact schema and vCard/QR/label rendering shared by the remote service and local agent."""
from __future__ import annotations

from dataclasses import dataclass

import qrcode
from PIL import Image, ImageDraw, ImageFont

# QL700 62mm continuous tape printable width, in dots (per brother_ql spec).
LABEL_WIDTH_PX = 696
LABEL_MARGIN_PX = 24
LABEL_FONT_SIZE = 32


@dataclass
class ContactData:
    name: str
    company: str = ""
    position: str = ""
    email: str = ""
    phone: str = ""
    url: str = ""
    consent: bool = False


def build_vcard(contact: ContactData) -> str:
    """Render a vCard 3.0 text block from the collected fields."""
    given, _, family = contact.name.strip().rpartition(" ")
    # N is required by vCard 3.0; without it some contact apps show ORG as the title instead of FN.
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"N:{family};{given};;;", f"FN:{contact.name}"]
    if contact.company:
        lines.append(f"ORG:{contact.company}")
    if contact.position:
        lines.append(f"TITLE:{contact.position}")
    if contact.phone:
        lines.append(f"TEL;TYPE=CELL:{contact.phone}")
    if contact.email:
        lines.append(f"EMAIL:{contact.email}")
    if contact.url:
        lines.append(f"URL:{contact.url}")
    lines.append("NOTE:Met at Ars Electronica Futurelab Networking Event. 2026")
    lines.append("END:VCARD")
    return "\r\n".join(lines)


def build_qr_image(vcard_text: str) -> Image.Image:
    """Render the vCard text as a QR code image."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2)
    qr.add_data(vcard_text)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Pillow < 10.1 load_default() has no size arg.
        return ImageFont.load_default()


def compose_label(qr_image: Image.Image, name: str) -> Image.Image:
    """Compose a 62mm-wide label: name centered above the QR code."""
    font = _label_font(LABEL_FONT_SIZE)
    qr_size = LABEL_WIDTH_PX - 2 * LABEL_MARGIN_PX
    qr_image = qr_image.resize((qr_size, qr_size))

    text_block_h = LABEL_FONT_SIZE + LABEL_MARGIN_PX
    label_height = text_block_h + qr_size + LABEL_MARGIN_PX

    label = Image.new("RGB", (LABEL_WIDTH_PX, label_height), "white")
    draw = ImageDraw.Draw(label)
    bbox = draw.textbbox((0, 0), name, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text(((LABEL_WIDTH_PX - text_w) // 2, LABEL_MARGIN_PX // 2), name, fill="black", font=font)
    label.paste(qr_image, (LABEL_MARGIN_PX, text_block_h))
    return label
