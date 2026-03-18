import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps
from barcode import Code128
from barcode.writer import ImageWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from pathlib import Path
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
# FUNCIONES AUXILIARES
# =========================================
def mm_to_px(mm: float, dpi: int = 203) -> int:
    return int(round((mm / 25.4) * dpi))


def scale_value(value, current_dpi, base_dpi=203):
    return int(round(value * current_dpi / base_dpi))


def resolve_font_path(bold: bool = False):
    """
    Busca una fuente TrueType real en Windows, Linux o carpeta local ./fonts
    """
    local_fonts_dir = Path("fonts")

    if bold:
        candidates = [
            str(local_fonts_dir / "DejaVuSans-Bold.ttf"),
            str(local_fonts_dir / "Arial-Bold.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            str(local_fonts_dir / "DejaVuSans.ttf"),
            str(local_fonts_dir / "Arial.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "DejaVuSans.ttf",
        ]

    for candidate in candidates:
        try:
            ImageFont.truetype(candidate, size=20)
            return candidate
        except Exception:
            continue

    return None


def load_font(size: int, bold: bool = False):
    """
    Carga una fuente TrueType real. Si no encuentra ninguna, lanza error.
    """
    font_path = resolve_font_path(bold)

    if font_path is None:
        raise RuntimeError(
            "No se encontró una fuente TrueType válida. "
            "Agrega archivos .ttf en una carpeta llamada 'fonts' "
            "o verifica las rutas de fuentes del sistema."
        )

    font = ImageFont.truetype(font_path, size=size)
    return font, font_path


def draw_rotated_text(base_image, text, xy, angle, font, fill="black", stroke_width=0, stroke_fill="black"):
    if not text:
        return base_image

    dummy = Image.new("RGBA", (10, 10), (255, 255, 255, 0))
    dummy_draw = ImageDraw.Draw(dummy)
    bbox = dummy_draw.textbbox(
        (0, 0),
        text,
        font=font,
        stroke_width=stroke_width
    )

    w = max(1, bbox[2] - bbox[0])
    h = max(1, bbox[3] - bbox[1])

    txt_img = Image.new("RGBA", (w + 30, h + 30), (255, 255, 255, 0))
    txt_draw = ImageDraw.Draw(txt_img)
    txt_draw.text(
        (15, 15),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill
    )

    rotated = txt_img.rotate(angle, expand=True)
    base_image.paste(rotated, xy, rotated)
    return base_image


def draw_multiline(draw, text, xy, font, fill="black", spacing=6, stroke_width=0, stroke_fill="black"):
    draw.multiline_text(
        xy,
        text,
        font=font,
        fill=fill,
        spacing=spacing,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill
    )


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


def convert_to_monochrome(image: Image.Image, threshold: int = 165, invert: bool = False) -> Image.Image:
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


def make_preview_image(image: Image.Image, zoom: float = 2.0) -> Image.Image:
    if zoom <= 1:
        return image

    new_w = int(image.width * zoom)
    new_h = int(image.height * zoom)
    return image.resize((new_w, new_h), Image.LANCZOS)


# =========================================
# SIDEBAR
# =========================================
with st.sidebar:
    st.header("Tamaño de la Etiqueta")
    label_width_mm = st.number_input("Ancho etiqueta (mm)", value=300.0, step=1.0)
    label_height_mm = st.number_input("Alto etiqueta (mm)", value=130.0, step=1.0)
    dpi = st.selectbox("DPI de trabajo / Impresora", [203, 300], index=1)

    st.header("Datos del Producto")
    codigo_principal = st.text_input("Clave GM", value="G10Z-416:FJ31")
    producto = st.text_input("Nombre Producto", value="BASE ROJO LACA:FJ31")
    lote = st.text_input("Lote", value="3DGLUB0D2")
    fecha = st.text_input("Fecha[DD/MM/AA]", value="26-Feb-2026")
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

    st.header("Texto e impresión")
    text_stroke = st.slider("Grosor del texto", min_value=0, max_value=4, value=2, step=1)

    st.header("Conversión a ZPL")
    threshold = st.slider("Umbral blanco/negro", min_value=100, max_value=220, value=165)

    st.header("Vista previa web")
    preview_zoom = st.slider("Zoom de vista previa", min_value=1.0, max_value=5.0, value=2.5, step=0.1)

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
draw = ImageDraw.Draw(label)

# =========================================
# FUENTES ESCALABLES
# =========================================
size_big = scale_value(53, dpi, BASE_DPI)
size_mid = scale_value(35, dpi, BASE_DPI)
size_tiny = scale_value(23, dpi, BASE_DPI)

try:
    font_big_bold, font_big_path = load_font(size_big, bold=True)
    font_mid_bold, font_mid_path = load_font(size_mid, bold=True)
    font_tiny, font_tiny_path = load_font(size_tiny, bold=False)
except RuntimeError as e:
    st.error(str(e))
    st.stop()

with st.sidebar:
    st.markdown("### Fuente cargada")
    st.write(f"Grande: {font_big_path}")
    st.write(f"Media: {font_mid_path}")
    st.write(f"Pequeña: {font_tiny_path}")

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
label = draw_rotated_text(label, codigo_principal, (x_codigo_principal, y_codigo_principal), 0, font_big_bold, stroke_width=text_stroke)
label = draw_rotated_text(label, producto, (x_producto, y_producto), 0, font_big_bold, stroke_width=text_stroke)

label = draw_rotated_text(label, lote, (x_lote, y_lote), 0, font_mid_bold, stroke_width=text_stroke)
label = draw_rotated_text(label, fecha, (x_fecha, y_fecha), 0, font_mid_bold, stroke_width=text_stroke)
label = draw_rotated_text(label, neto, (x_neto, y_neto), 0, font_mid_bold, stroke_width=text_stroke)
label = draw_rotated_text(label, bruto, (x_bruto, y_bruto), 0, font_mid_bold, stroke_width=text_stroke)

draw_multiline(draw, destino, (x_destino, y_destino), font_tiny, fill="black", spacing=5, stroke_width=1)

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
# VISTA PREVIA COLOR
# =========================================
st.subheader("Vista previa de la etiqueta")
st.write(f"Resolución real de la etiqueta: {label.width} × {label.height} px")

preview_label = make_preview_image(label, zoom=preview_zoom)
st.image(
    preview_label,
    caption=f"Vista previa ampliada x{preview_zoom:.1f}",
    use_container_width=False
)

# =========================================
# CONVERSIÓN A ZPL
# =========================================
bw_img = convert_to_monochrome(label, threshold=threshold, invert=False)

st.subheader("Vista previa 1-bit para Zebra")
preview_bw = make_preview_image(bw_img.convert("RGB"), zoom=preview_zoom)
st.image(
    preview_bw,
    caption=f"Vista previa Zebra ampliada x{preview_zoom:.1f}",
    use_container_width=False
)

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
    st.download_button("📷 Descargar PNG", data=png_buffer, file_name="Etiqueta_Final.png", mime="image/png")

with col2:
    st.download_button("📑 Descargar PDF", data=pdf_buffer, file_name="Etiqueta_Final.pdf", mime="application/pdf")

with col3:
    st.download_button("🖨️ Descargar ZPL", data=zpl_bytes, file_name="Etiqueta_Final.zpl", mime="application/octet-stream")

st.subheader("Vista previa del ZPL")
st.text_area("ZPL generado", zpl_code[:5000], height=300)

st.subheader("Datos técnicos")
st.write(f"**Tamaño etiqueta:** {label_width_mm} mm × {label_height_mm} mm")
st.write(f"**Resolución de Impresión:** {dpi} DPI")
st.write(f"**Tamaño final en dots:** {final_width_px} × {final_height_px}")
st.write(f"**Rotación aplicada:** {rotation_option}")
st.write(f"**Escalado respecto a {BASE_DPI} DPI:** {dpi / BASE_DPI:.4f}x")
st.write(f"**Tamaño ZPL ASCII:** {len(zpl_bytes) / 1024:.2f} KB")
