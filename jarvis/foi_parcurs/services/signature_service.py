"""AI signature SVG generation for foi de parcurs contracts."""


def generate_ai_signature(advisor_name: str, variant: int = 1) -> str:
    """Generate SVG signature as styled text. Returns raw SVG string."""
    initials = "".join(
        [word[0].upper() for word in advisor_name.split() if word]
    )

    variants = {
        1: ('Lucida Handwriting, cursive', '24px', 'italic', 'normal', ''),
        2: ('Brush Script MT, cursive', '28px', 'normal', 'normal', ''),
        3: ('Segoe Print, cursive', '22px', 'normal', 'bold', ''),
        4: ('Georgia, serif', '20px', 'italic', 'bold', 'letter-spacing: 3px;'),
        5: ('Palatino, serif', '26px', 'italic', 'normal', 'letter-spacing: 2px;'),
    }

    v = variant % 5 or 5
    font_family, font_size, font_style, font_weight, extra = variants[v]

    svg = (
        f'<svg width="200" height="60" xmlns="http://www.w3.org/2000/svg">\n'
        f'  <text x="10" y="42" style="font-family: {font_family}; '
        f'font-size: {font_size}; font-style: {font_style}; '
        f'font-weight: {font_weight}; fill: #1a1a2e; {extra}">'
        f'{initials}</text>\n'
        f'  <line x1="10" y1="48" x2="120" y2="48" '
        f'stroke="#1a1a2e" stroke-width="0.5" opacity="0.4"/>\n'
        f'</svg>'
    )
    return svg
