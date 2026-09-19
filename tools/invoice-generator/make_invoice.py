#!/usr/bin/env python3
"""
Generate a Parker Compositions invoice PDF matching the brand template exactly
(coordinates/fonts/sizes measured from the original PDF via pdfplumber).
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

BLACK = HexColor("#0A0A0A")
PAGE_W, PAGE_H = letter  # 612 x 792

pdfmetrics.registerFont(TTFont("RockSalt", "RockSalt-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Poppins-Regular", "/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Poppins-Light", "/usr/share/fonts/truetype/google-fonts/Poppins-Light.ttf"))
pdfmetrics.registerFont(TTFont("Poppins-SemiBold", "Poppins-SemiBold.ttf"))

TRACK = 0.0997  # measured letter-spacing ratio (~10% of font size) across every text element


def draw_tracked(c, text, x, y, font, size, align="left"):
    tracking = size * TRACK
    widths = [pdfmetrics.stringWidth(ch, font, size) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1 if len(text) > 1 else 0)
    if align == "right":
        x = x - total
    elif align == "center":
        x = x - total / 2
    c.setFont(font, size)
    cx = x
    for ch, w in zip(text, widths):
        c.drawString(cx, y, ch)
        cx += w + tracking


# ---- measured layout constants ----
MARGIN_L = 82.2
RIGHT_X = 529.4
COL_RATE_CX = 330.3
COL_HOURS_CX = 406.55

HEADER_UNDERLINE_Y = 444.6
ROW_LINE_YS = [410.4, 377.5, 344.55, 311.5, 278.3]  # 5 fixed row slots
SUBTOTAL_LINE_Y = 222.7

ROW_TEXT_OFFSET = 9.9   # baseline = row_line_y + offset
HEADER_TEXT_OFFSET = 13.1


def draw_invoice(filename, data):
    c = canvas.Canvas(filename, pagesize=letter)
    c.setFillColor(BLACK)
    c.setStrokeColor(BLACK)

    # ---- Header ----
    # Note: nudged up/down vs. raw measured coordinates so the RockSalt "E" tail
    # doesn't collide with the invoice number underneath it.
    draw_tracked(c, "INVOICE", RIGHT_X + 0.9, 703.0, "RockSalt", 27, align="right")
    draw_tracked(c, f"#{data['invoice_number']}", RIGHT_X + 0.5, 663.0, "Poppins-Regular", 11.29, align="right")

    # ---- Optional pay-here QR code, top-left corner ----
    qr = data.get("qr_code")
    if qr:
        qr_size = 58
        qr_x = MARGIN_L + 20
        qr_y = 726 - qr_size + 15
        c.drawImage(qr["path"], qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True, mask="auto")
        draw_tracked(c, qr.get("caption", "Pay here with PayPal!"), qr_x + qr_size / 2, qr_y - 13, "Poppins-SemiBold", 8.5, align="center")

    # ---- Billed To / Pay To ----
    draw_tracked(c, "BILLED TO:", MARGIN_L, 632.0, "Poppins-SemiBold", 12)
    draw_tracked(c, data["billed_to"], 196.9, 631.9, "Poppins-Regular", 11.29)

    draw_tracked(c, "PAY TO:", MARGIN_L, 605.4, "Poppins-SemiBold", 12)
    draw_tracked(c, "Parker Compositions: Attn Sarah Griego", 196.7, 606.4, "Poppins-Regular", 11.29)
    draw_tracked(c, "300 Amber Ridge Rd. Jacksonville, FL", 196.9, 589.1, "Poppins-Regular", 11.29)
    draw_tracked(c, "(505)-999-0671", 196.9, 573.6, "Poppins-Regular", 11.29)

    draw_tracked(c, data.get("account_name_label", "Account Name"), MARGIN_L, 535.7, "Poppins-Regular", 11.29)

    # ---- Table header ----
    hy = 792 - 334.3
    draw_tracked(c, "DESCRIPTION", MARGIN_L, hy, "Poppins-SemiBold", 11.29)
    draw_tracked(c, "RATE", COL_RATE_CX, hy, "Poppins-SemiBold", 11.29, align="center")
    draw_tracked(c, "HOURS", COL_HOURS_CX, hy, "Poppins-SemiBold", 11.29, align="center")
    draw_tracked(c, "AMOUNT", RIGHT_X, hy, "Poppins-SemiBold", 11.29, align="right")

    c.setLineWidth(0.75)
    c.line(MARGIN_L, HEADER_UNDERLINE_Y, RIGHT_X, HEADER_UNDERLINE_Y)

    # ---- Row content ----
    rows = list(data["lines"])
    rows.append({"desc": "Editing/formatting", "rate": "N/A", "hours": "N/A", "amount": "Comp"})
    while len(rows) < 5:
        rows.append(None)
    rows = rows[:5]

    DESC_MAX_WIDTH = 300 - MARGIN_L  # keep clear of the RATE column

    def fit_desc_size(text, base_size=10.34, min_size=6.5):
        size = base_size
        while size > min_size:
            tracking = size * TRACK
            widths = [pdfmetrics.stringWidth(ch, "Poppins-Light", size) for ch in text]
            total = sum(widths) + tracking * (len(text) - 1 if len(text) > 1 else 0)
            if total <= DESC_MAX_WIDTH:
                return size
            size -= 0.25
        return min_size

    DESC_LINE_GAP = 12.5
    CENTER_SHIFT_PER_EXTRA_LINE = 4.14  # calibrated (render + measure) so a 2-line description sits centered in its row

    row_tops = [HEADER_UNDERLINE_Y] + ROW_LINE_YS[:-1]

    for row_top, line_y, row in zip(row_tops, ROW_LINE_YS, rows):
        if row:
            ty = line_y + ROW_TEXT_OFFSET
            desc = row["desc"]
            if "\n" in desc:
                # explicit multi-line description, drawn at full row-text size,
                # with the whole row's content (desc + rate/hours/amount) shifted
                # up as a block so it sits vertically centered in the row.
                desc_lines = desc.split("\n")
                n = len(desc_lines)
                row_ty = ty - (n - 1) * CENTER_SHIFT_PER_EXTRA_LINE
                for i, dline in enumerate(desc_lines):
                    line_ty = row_ty + (n - 1 - i) * DESC_LINE_GAP
                    draw_tracked(c, dline, MARGIN_L, line_ty, "Poppins-Light", 10.34)
            else:
                row_ty = ty
                desc_size = fit_desc_size(desc)
                # keep the shrunk description text vertically centered on the same baseline zone
                desc_ty = ty - (10.34 - desc_size) * 0.15
                draw_tracked(c, desc, MARGIN_L, desc_ty, "Poppins-Light", desc_size)
            draw_tracked(c, row["rate"], COL_RATE_CX, row_ty, "Poppins-Light", 10.34, align="center")
            draw_tracked(c, row["hours"], COL_HOURS_CX, row_ty, "Poppins-Light", 10.34, align="center")
            draw_tracked(c, row["amount"], RIGHT_X, row_ty, "Poppins-Light", 10.34, align="right")
        c.setLineWidth(0.5)
        c.line(MARGIN_L, line_y, RIGHT_X, line_y)

    # ---- Sub-total / Total ----
    draw_tracked(c, "Sub-Total", MARGIN_L, 239.1, "Poppins-Light", 11.29)
    draw_tracked(c, data["subtotal"], RIGHT_X, 239.1, "Poppins-Light", 11.29, align="right")
    c.setLineWidth(0.75)
    c.line(MARGIN_L, SUBTOTAL_LINE_Y, RIGHT_X, SUBTOTAL_LINE_Y)

    draw_tracked(c, "TOTAL", MARGIN_L, 193.1, "Poppins-SemiBold", 13.17)
    draw_tracked(c, data["total"], RIGHT_X, 191.9, "Poppins-SemiBold", 13.17, align="right")

    # ---- Terms ----
    draw_tracked(c, "Payment is required within 45 business days of the invoice date.", MARGIN_L, 153.6, "Poppins-Light", 11.29)
    draw_tracked(c, "Please send remittance to parkercompositions@gmail.com.", MARGIN_L, 138.1, "Poppins-Light", 11.29)
    draw_tracked(c, "Thank you for your business.", MARGIN_L, 107.1, "Poppins-Light", 11.29)

    # ---- Signature ----
    c.drawImage(
        data["signature_path"], 79.2, 47.73, width=150, height=49.5,
        preserveAspectRatio=True, mask="auto"
    )
    draw_tracked(c, "Sarah Griego, Owner", 85.2, 27.0, "Poppins-Light", 10.34)

    c.showPage()
    c.save()
