"""Genera dos .ico custom para los accesos directos de los .bat.
Uso puntual: python _make_icons.py
"""
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
S = 256  # lienzo base; el .ico guarda varios tamanos


def rounded_bg(color, radius=56):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, S - 8, S - 8], radius=radius, fill=color)
    return img, d


ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
STATIC = HERE / "backend" / "static"


def streamlit_img():
    img, d = rounded_bg((255, 75, 75, 255))  # #FF4B4B
    # tres barras ascendentes (chart) en blanco
    bar_w = 34
    xs = [70, 120, 170]
    heights = [70, 110, 150]
    base = 188
    for x, h in zip(xs, heights):
        d.rounded_rectangle([x, base - h, x + bar_w, base], radius=8,
                            fill=(255, 255, 255, 255))
    return img


def backend_img():
    img, d = rounded_bg((5, 153, 139, 255))  # #05998b (FastAPI teal)
    # rayo (lightning bolt) blanco
    bolt = [
        (150, 40), (95, 140), (135, 140),
        (110, 216), (180, 110), (138, 110),
    ]
    d.polygon(bolt, fill=(255, 255, 255, 255))
    return img


if __name__ == "__main__":
    st_img = streamlit_img()
    be_img = backend_img()

    # Iconos para los accesos directos (.lnk)
    st_img.save(HERE / "icon_streamlit.ico", sizes=ICO_SIZES)
    be_img.save(HERE / "icon_backend.ico", sizes=ICO_SIZES)

    # Favicon (nav icon) Streamlit legacy -> PNG para st.set_page_config(page_icon=...)
    st_img.resize((192, 192)).save(HERE / "favicon_streamlit.png")

    # Favicon (nav icon) backend FastAPI -> static/favicon.ico + PNG
    STATIC.mkdir(parents=True, exist_ok=True)
    be_img.save(STATIC / "favicon.ico", sizes=ICO_SIZES)
    be_img.resize((192, 192)).save(STATIC / "favicon.png")

    for p in ("icon_streamlit.ico", "icon_backend.ico", "favicon_streamlit.png"):
        print("OK ->", HERE / p)
    print("OK ->", STATIC / "favicon.ico")
    print("OK ->", STATIC / "favicon.png")
