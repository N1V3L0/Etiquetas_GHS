import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps
from barcode import Code128
from barcode.writer import ImageWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
import os
import tempfile
import math
import binascii

# =========================================
# CONFIGURACIÓN DE VISUALIZACIÓN
# =========================================
st.set_page_config(page_title="Editor de Etiquetas + ZPL", layout="wide")

st.markdown(
    """
    <h1 style='
        color:#1E3A8A;
        text-align:center;
        font-size:42px;
        font-family:Arial, sans-serif;
        font-weight:bold;
        margin-bottom:20px;
    '>
    🏷️ Editor de Etiquetas con salida ZPL
    </h1>
    """,
    unsafe_allow_html=True
)

st.markdown(
    "<p style='text-align:center; font-size:18px; color:#555;'>Sube una plantilla, captura los datos del producto y genera la etiqueta final en PNG, PDF y ZPL.</p>",
    unsafe_allow_html=True
)

BASE_DPI = 203

# =========================================
# FUENTES LOCALES DEL PROYECTO
# =========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FONT_REGULAR_PATH = os.path.join(BASE_DIR, "DejaVuSans.ttf")
FONT_BOLD_PATH = os.path.join(BASE_DIR, "DejaVuSans-Bold.ttf")

# =========================================
# FUNCIONES AUXILIARES
# =========================================
def mm_to_px(mm: float, dpi: int = 203) -> int:
    return int(round((mm / 25.4) * dpi))


def scale_value(value, current_dpi, base_dpi=203):
    return int(round(value * current_dpi / base_dpi))


def ensure_fonts_exist():
    missing = []
    if not os.path.exists(FONT_REGULAR_PATH):
        missing.append(FONT_REGULAR_PATH)
    if not os.path.exists(FONT_BOLD_PATH):
        missing.append(FONT_BOLD_PATH)
    return missing


def load_font(size: int, bold: bool = False):
    font_path = FONT_BOLD_PATH if bold else FONT_REGULAR_PATH
    return ImageFont.truetype(font_path, size=size)


def draw_text(base_image, text, xy, font, fill="black", stroke_width=0, stroke_fill="black"):
    if not text:
        return base_image

    overlay = Image.new("RGBA", base_image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    draw.text(
        xy,
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill
    )
    return Image.alpha_composite(base_image, overlay)


def draw_multiline(base_image, text, xy, font, fill="black", spacing=6, stroke_width=0, stroke_fill="black"):
    if not text:
        return base_image

    overlay = Image.new("RGBA", base_image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    draw.multiline_text(
        xy,
        text,
        font=font,
        fill=fill,
        spacing=spacing,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill
    )
    return Image.alpha_composite(base_image, overlay)


def sanitize_barcode_value(value: str) -> str:
    if value is None:
        return ""
    return str(value).strip()


def generate_barcode(
    code_value: str,
    module_width=0.2,
    module_height=30,
    font_size=10,
    text_distance=2
):
    if not code_value:
        return None

    clean_value = sanitize_barcode_value(code_value)

    with tempfile.TemporaryDirectory() as tmpdir:
        barcode_path = os.path.join(tmpdir, "barcode")
        barcode_obj = Code128(clean_value, writer=ImageWriter())

        options = {
            "module_width": module_width,
            "module_height": module_height,
            "font_size": font_size,
            "text_distance": text_distance,
            "quiet_zone": 2,
            "dpi": 300,
            "write_text": True,
        }

        filename = barcode_obj.save(barcode_path, options=options)
        img = Image.open(filename).convert("RGBA")
        return img.copy()


def paste_barcode(base_image, barcode_image, x, y, width=None, height=None, angle=0):
    if barcode_image is None:
        return base_image

    img = barcode_image.copy()

    if width is not None and height is not None:
        img = img.resize((width, height), Image.LANCZOS)

    if angle != 0:
        img = img.rotate(angle, expand=True)

    base_image.paste(img, (x, y), img)
    return base_image


def export_to_pdf(pil_image: Image.Image, pdf_width_mm: float, pdf_height_mm: float):
    img_buffer = io.BytesIO()
    pdf_buffer = io.BytesIO()

    pil_rgb = pil_image.convert("RGB")
    pil_rgb.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    width_pt = pdf_width_mm * 72 / 25.4
    height_pt = pdf_height_mm * 72 / 25.4

    c = canvas.Canvas(pdf_buffer, pagesize=(width_pt, height_pt))
    c.drawImage(ImageReader(img_buffer), 0, 0, width=width_pt, height=height_pt)
    c.save()

    pdf_buffer.seek(0)
    return pdf_buffer


def convert_to_monochrome(image: Image.Image, threshold: int = 180, invert: bool = False) -> Image.Image:
    gray = image.convert("L")
    bw = gray.point(lambda x: 255 if x > threshold else 0, mode="1")

    if invert:
        bw = ImageOps.invert(bw.convert("L")).convert("1")

    return bw


def image_to_zpl_graphic_hex(image_bw: Image.Image):
    if image_bw.mode != "1":
        raise ValueError("La imagen debe estar en modo 1-bit ('1').")

    width, height = image_bw.size
    bytes_per_row = math.ceil(width / 8)

    pixels = image_bw.load()
    hex_rows = []

    for y in range(height):
        row_bytes = bytearray()
        current_byte = 0
        bit_count = 0

        for x in range(width):
            pixel = pixels[x, y]
            bit = 0 if pixel == 255 else 1

            current_byte = (current_byte << 1) | bit
            bit_count += 1

            if bit_count == 8:
                row_bytes.append(current_byte)
                current_byte = 0
                bit_count = 0

        if bit_count > 0:
            current_byte = current_byte << (8 - bit_count)
            row_bytes.append(current_byte)

        hex_row = binascii.hexlify(row_bytes).decode("ascii").upper()
        hex_rows.append(hex_row)

    hex_data = "".join(hex_rows)
    total_bytes = bytes_per_row * height
    return total_bytes, bytes_per_row, hex_data


def build_zpl_from_image(
    image_bw: Image.Image,
    label_width_px: int,
    label_height_px: int,
    offset_x: int = 0,
    offset_y: int = 0
) -> str:
    total_bytes, bytes_per_row, hex_data = image_to_zpl_graphic_hex(image_bw)

    zpl = f"""^XA
^PW{label_width_px}
^LL{label_height_px}
^LH0,0
^FO{offset_x},{offset_y}
^GFA,{total_bytes},{total_bytes},{bytes_per_row},{hex_data}
^XZ
"""
    return zpl

# =========================================
# VALIDAR FUENTES
# =========================================
missing_fonts = ensure_fonts_exist()
if missing_fonts:
    st.error(
        "Faltan fuentes TTF en tu proyecto. Verifica la carpeta fonts/ y estos archivos:\n\n"
        + "\n".join(missing_fonts)
    )
    st.stop()

# =========================================
# SIDEBAR
# =========================================
with st.sidebar:
    st.header("Tamaño de la Etiqueta")
    label_width_mm = st.number_input("Ancho etiqueta (mm)", value=300.0, step=1.0)
    label_height_mm = st.number_input("Alto etiqueta (mm)", value=130.0, step=1.0)
    dpi = st.selectbox("DPI de trabajo / Impresora", [203, 300], index=0)

    st.header("Datos del Producto")
    codigo_principal = st.text_input("Clave GM", value="G10Z-416:FJ31")
    producto = st.text_input("Nombre Producto", value="BASE ROJO LACA:FJ31")
    lote = st.text_input("Lote", value="3DGLUB0D2")
    fecha = st.text_input("Fecha [DD/MM/AA]", value="26-Feb-2026")
    neto = st.text_input("Peso Neto [Kg]", value="17.00 KG")
    bruto = st.text_input("Peso Bruto [Kg]", value="18.8 KG")
    numero_articulo = st.text_input("Número del Artículo", value="90337725")

    destino = st.text_area(
        "Destino",
        value="NOMBRE \nDIRECCION \nCOLONIA \nCIUDAD, MUNICIPIO, CP.",
        height=120,
    )

    st.header("Rotación final")
    rotation_option = st.selectbox(
        "Rotación de la etiqueta",
        ["0°", "90° izquierda", "90° derecha", "180°"]
    )

    st.header("Conversión a ZPL")
    threshold = st.slider("Umbral blanco/negro", min_value=50, max_value=250, value=180)
    invert_colors = st.checkbox("Invertir colores", value=False)

# =========================================
# CARGA DE PLANTILLA
# =========================================
uploaded_template = st.file_uploader(
    "Sube tu plantilla base (PNG, JPG o JPEG)",
    type=["png", "jpg", "jpeg"]
)

if uploaded_template is None:
    st.info("Sube una plantilla para continuar.")
    st.stop()

try:
    template = Image.open(uploaded_template).convert("RGBA")
except Exception as e:
    st.error(f"No se pudo abrir la plantilla: {e}")
    st.stop()

# =========================================
# AJUSTE DE TAMAÑO
# =========================================
target_width_px = mm_to_px(label_width_mm, dpi)
target_height_px = mm_to_px(label_height_mm, dpi)

try:
    template = template.resize((target_width_px, target_height_px), Image.LANCZOS)
except Exception as e:
    st.error(f"No se pudo redimensionar la plantilla: {e}")
    st.stop()

label = template.copy()

# =========================================
# FUENTES ORIGINALES
# =========================================
size_big = scale_value(53, dpi, BASE_DPI)
size_mid = scale_value(35, dpi, BASE_DPI)
size_tiny = scale_value(23, dpi, BASE_DPI)

font_big_bold = load_font(size_big, bold=True)
font_mid_bold = load_font(size_mid, bold=True)
font_tiny = load_font(size_tiny, bold=False)

# =========================================
# COORDENADAS ESCALABLES
# =========================================
x_codigo_principal = scale_value(48, dpi, BASE_DPI)
y_codigo_principal = scale_value(142, dpi, BASE_DPI)

x_producto = scale_value(48, dpi, BASE_DPI)
y_producto = scale_value(239, dpi, BASE_DPI)

x_lote = scale_value(290, dpi, BASE_DPI)
y_lote = scale_value(494, dpi, BASE_DPI)

x_fecha = scale_value(290, dpi, BASE_DPI)
y_fecha = scale_value(566, dpi, BASE_DPI)

x_neto = scale_value(290, dpi, BASE_DPI)
y_neto = scale_value(641, dpi, BASE_DPI)

x_bruto = scale_value(290, dpi, BASE_DPI)
y_bruto = scale_value(735, dpi, BASE_DPI)

x_destino = scale_value(672, dpi, BASE_DPI)
y_destino = scale_value(660, dpi, BASE_DPI)

x_bar_top = scale_value(19, dpi, BASE_DPI)
y_bar_top = scale_value(482, dpi, BASE_DPI)
w_bar_top = scale_value(419, dpi, BASE_DPI)
h_bar_top = scale_value(160, dpi, BASE_DPI)

x_bar_side = scale_value(532, dpi, BASE_DPI)
y_bar_side = scale_value(557, dpi, BASE_DPI)
w_bar_side = scale_value(279, dpi, BASE_DPI)
h_bar_side = scale_value(127, dpi, BASE_DPI)

x_bar_dest = scale_value(706, dpi, BASE_DPI)
y_bar_dest = scale_value(490, dpi, BASE_DPI)
w_bar_dest = scale_value(384, dpi, BASE_DPI)
h_bar_dest = scale_value(119, dpi, BASE_DPI)

# =========================================
# GENERAR CÓDIGOS DE BARRAS
# =========================================
barcode_top = generate_barcode(
    lote,
    module_width=0.22,
    module_height=38,
    font_size=10,
    text_distance=2,
)

barcode_side = generate_barcode(
    neto,
    module_width=0.22,
    module_height=28,
    font_size=10,
    text_distance=2,
)

barcode_dest = generate_barcode(
    numero_articulo,
    module_width=0.22,
    module_height=28,
    font_size=10,
    text_distance=2,
)

# =========================================
# PEGAR CÓDIGOS DE BARRAS
# =========================================
label = paste_barcode(label, barcode_top, x_bar_top, y_bar_top, w_bar_top, h_bar_top, angle=90)
label = paste_barcode(label, barcode_side, x_bar_side, y_bar_side, w_bar_side, h_bar_side, angle=90)
label = paste_barcode(label, barcode_dest, x_bar_dest, y_bar_dest, w_bar_dest, h_bar_dest, angle=0)

# =========================================
# DIBUJO DE TEXTO
# =========================================
label = draw_text(label, codigo_principal, (x_codigo_principal, y_codigo_principal), font_big_bold)
label = draw_text(label, producto, (x_producto, y_producto), font_big_bold)

label = draw_text(label, lote, (x_lote, y_lote), font_mid_bold)
label = draw_text(label, fecha, (x_fecha, y_fecha), font_mid_bold)
label = draw_text(label, neto, (x_neto, y_neto), font_mid_bold)
label = draw_text(label, bruto, (x_bruto, y_bruto), font_mid_bold)

label = draw_multiline(label, destino, (x_destino, y_destino), font_tiny, spacing=5)

# =========================================
# ROTACIÓN FINAL
# =========================================
if rotation_option == "90° izquierda":
    label = label.rotate(90, expand=True)
elif rotation_option == "90° derecha":
    label = label.rotate(-90, expand=True)
elif rotation_option == "180°":
    label = label.rotate(180, expand=True)

# =========================================
# VISTA PREVIA SIMPLE
# =========================================
st.subheader("Vista previa de la etiqueta")
st.image(label, use_container_width=True)

# =========================================
# CONVERSIÓN A ZPL
# =========================================
bw_img = convert_to_monochrome(label, threshold=threshold, invert=invert_colors)

final_width_px, final_height_px = bw_img.size
zpl_code = build_zpl_from_image(
    bw_img,
    label_width_px=final_width_px,
    label_height_px=final_height_px,
    offset_x=0,
    offset_y=0
)

# =========================================
# DESCARGAS
# =========================================
png_buffer = io.BytesIO()
label.convert("RGB").save(png_buffer, format="PNG")
png_buffer.seek(0)

pdf_buffer = export_to_pdf(label, label_width_mm, label_height_mm)
zpl_bytes = zpl_code.encode("ascii", errors="ignore")

col1, col2, col3 = st.columns(3)

with col1:
    st.download_button(
        "📷 Descargar PNG",
        data=png_buffer,
        file_name="Etiqueta_Final.png",
        mime="image/png"
    )

with col2:
    st.download_button(
        "📑 Descargar PDF",
        data=pdf_buffer,
        file_name="Etiqueta_Final.pdf",
        mime="application/pdf"
    )

with col3:
    st.download_button(
        "🖨️ Descargar ZPL",
        data=zpl_bytes,
        file_name="Etiqueta_Final.zpl",
        mime="application/octet-stream"
    )

st.subheader("Datos técnicos")
st.write(f"**Tamaño etiqueta:** {label_width_mm} mm × {label_height_mm} mm")
st.write(f"**Resolución de Impresión:** {dpi} DPI")
st.write(f"**Tamaño final en dots:** {final_width_px} × {final_height_px}")
st.write(f"**Rotación aplicada:** {rotation_option}")
st.write(f"**Tamaño ZPL ASCII:** {len(zpl_bytes) / 1024:.2f} KB")