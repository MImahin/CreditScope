"""Printable CreditScope dashboard reports."""
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)
from reportlab.graphics.shapes import Drawing, Rect, String

from .analytics import FILTERS


INK = HexColor('#18302d')
MUTED = HexColor('#6f827b')
TEAL = HexColor('#14776a')
MINT = HexColor('#e7f3ec')
LINE = HexColor('#dce7e1')
ROSE = HexColor('#c98279')
BG = HexColor('#f4f7f5')


def _fmt_number(value):
    return '-' if value is None else f'{value:,.0f}'


def _fmt_compact(value):
    if value is None:
        return '-'
    if abs(value) >= 1_000_000:
        return f'{value / 1_000_000:.2f}M'
    if abs(value) >= 1_000:
        return f'{value / 1_000:.2f}K'
    return f'{value:,.0f}'


def _fmt_pct(value, digits=2):
    return '-' if value is None else f'{value * 100:.{digits}f}%'


def _paragraph(text, style):
    return Paragraph(str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), style)


def _metric_card(label, value, note, styles, accent=False):
    value_style = styles['MetricAccent'] if accent else styles['Metric']
    card = Table([
        [_paragraph(label.upper(), styles['MetricLabel'])],
        [_paragraph(value, value_style)],
        [_paragraph(note, styles['MetricNote'])],
    ], colWidths=[49 * mm], rowHeights=[7 * mm, 14 * mm, 8 * mm])
    card.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), MINT if accent else colors.white),
        ('BOX', (0, 0), (-1, -1), .6, LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
        ('TOPPADDING', (0, 0), (-1, -1), 1.2 * mm),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.2 * mm),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return card


def _vertical_chart(rows, width=345, height=155):
    drawing = Drawing(width, height)
    left, bottom, top = 35, 28, height - 12
    plot_h = top - bottom
    maximum = max([row['rate'] or 0 for row in rows] + [.01]) * 1.18
    for index, tick in enumerate([0, .25, .5, .75, 1]):
        y = bottom + plot_h * tick
        drawing.add(Rect(left, y, width-left-8, .4, fillColor=LINE, strokeColor=None))
        drawing.add(String(2, y-3, _fmt_pct(maximum*tick, 0), fontName='Helvetica', fontSize=6.5, fillColor=MUTED))
    gap = 8
    bar_w = max(18, (width-left-12-gap*(len(rows)-1))/max(len(rows), 1))
    for index, row in enumerate(rows):
        rate = row['rate'] or 0
        x = left + index * (bar_w + gap)
        bar_h = rate / maximum * plot_h
        drawing.add(Rect(x, bottom, bar_w, bar_h, fillColor=TEAL if index == 0 else HexColor('#8fbfa8'), strokeColor=None))
        drawing.add(String(x+bar_w/2, bottom+bar_h+4, _fmt_pct(rate, 1), textAnchor='middle', fontName='Helvetica-Bold', fontSize=7, fillColor=INK))
        label = str(row['group']).replace('(', '').replace(']', '').replace(', ', '-')
        drawing.add(String(x+bar_w/2, 12, label, textAnchor='middle', fontName='Helvetica', fontSize=6.5, fillColor=MUTED))
    return drawing


def _horizontal_chart(rows, width=345, height=155):
    drawing = Drawing(width, height)
    label_w, right = 102, 35
    maximum = max([row['rate'] or 0 for row in rows] + [.01]) * 1.12
    row_h = min(22, (height-16)/max(len(rows), 1))
    for index, row in enumerate(rows):
        y = height - 16 - index * row_h
        rate = row['rate'] or 0
        label = str(row['group']).replace('×', 'x').replace('–', '-')
        drawing.add(String(0, y, label, fontName='Helvetica', fontSize=7.2, fillColor=MUTED))
        drawing.add(Rect(label_w, y-1, width-label_w-right, 7, fillColor=HexColor('#edf3ef'), strokeColor=None))
        drawing.add(Rect(label_w, y-1, (width-label_w-right)*rate/maximum, 7, fillColor=HexColor('#68a487'), strokeColor=None))
        drawing.add(String(width-2, y, _fmt_pct(rate, 1), textAnchor='end', fontName='Helvetica-Bold', fontSize=7.2, fillColor=INK))
    return drawing


def _matrix(data, styles):
    ages = sorted({str(row['age']) for row in data})
    incomes = sorted({str(row['income']) for row in data})
    lookup = {(str(row['age']), str(row['income'])): row for row in data}
    cells = [[_paragraph('AGE / INCOME', styles['MatrixColumnHead'])] + [_paragraph(i.replace(' Lowest','').replace(' Highest',''), styles['MatrixColumnHead']) for i in incomes]]
    rates = [row['rate'] for row in data if row['rate'] is not None]
    maximum = max(rates + [.01])
    for age in ages:
        cells.append([_paragraph(age.replace('(', '').replace(']', '').replace(', ', '-'), styles['MatrixHead'])] + [
            _paragraph(_fmt_pct(lookup[(age, income)]['rate'], 1), styles['MatrixCell']) if (age, income) in lookup else _paragraph('-', styles['MatrixCell'])
            for income in incomes
        ])
    table = Table(cells, colWidths=[30*mm] + [20*mm]*len(incomes), rowHeights=7*mm)
    rules = [('GRID',(0,0),(-1,-1),.5,colors.white),('BACKGROUND',(0,0),(-1,0),INK),('TEXTCOLOR',(0,0),(-1,0),colors.white),('BACKGROUND',(0,1),(0,-1),BG),('VALIGN',(0,0),(-1,-1),'MIDDLE')]
    for row_index, age in enumerate(ages, start=1):
        for col_index, income in enumerate(incomes, start=1):
            item = lookup.get((age, income))
            alpha = (item['rate'] or 0) / maximum if item else 0
            color = colors.Color(0.91-.28*alpha, 0.96-.19*alpha, 0.92-.24*alpha)
            rules.append(('BACKGROUND',(col_index,row_index),(col_index,row_index),color))
    table.setStyle(TableStyle(rules))
    return table


def build_dashboard_report(summary, filters):
    """Return a complete dashboard PDF as bytes."""
    buffer = BytesIO()
    page_width, page_height = landscape(A4)
    doc = SimpleDocTemplate(buffer, pagesize=(page_width, page_height), leftMargin=16*mm,
                            rightMargin=16*mm, topMargin=18*mm, bottomMargin=15*mm,
                            title='CreditScope Executive Dashboard Report', author='CreditScope')
    base = getSampleStyleSheet()
    styles = {
        'Title': ParagraphStyle('ReportTitle', parent=base['Title'], fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=INK, alignment=TA_LEFT, spaceAfter=2*mm),
        'Subtitle': ParagraphStyle('Subtitle', parent=base['Normal'], fontName='Helvetica', fontSize=8.5, leading=12, textColor=MUTED),
        'Section': ParagraphStyle('Section', parent=base['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=15, textColor=INK, spaceAfter=2*mm),
        'Body': ParagraphStyle('Body', parent=base['Normal'], fontName='Helvetica', fontSize=8, leading=11, textColor=MUTED),
        'MetricLabel': ParagraphStyle('MetricLabel', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=6.5, leading=8, textColor=MUTED),
        'Metric': ParagraphStyle('Metric', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=18, leading=20, textColor=INK),
        'MetricAccent': ParagraphStyle('MetricAccent', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=18, leading=20, textColor=TEAL),
        'MetricNote': ParagraphStyle('MetricNote', parent=base['Normal'], fontName='Helvetica', fontSize=6.2, leading=8, textColor=MUTED),
        'MatrixHead': ParagraphStyle('MatrixHead', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=6.5, leading=8, alignment=TA_LEFT, textColor=INK),
        'MatrixColumnHead': ParagraphStyle('MatrixColumnHead', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=6.5, leading=8, alignment=TA_LEFT, textColor=colors.white),
        'MatrixCell': ParagraphStyle('MatrixCell', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=8, alignment=TA_RIGHT, textColor=INK),
    }
    active = [(FILTERS[key][1], value) for key, value in filters if value]
    filter_text = ' | '.join(f'{label}: {value}' for label, value in active) if active else 'All applicants - no filters applied'
    generated = datetime.now().strftime('%d %b %Y, %I:%M %p')
    story = [
        _paragraph('CreditScope', styles['Subtitle']),
        _paragraph('Executive Dashboard Report', styles['Title']),
        _paragraph(f'Generated {generated} | {filter_text}', styles['Subtitle']),
        Spacer(1, 5*mm),
    ]
    cards = [
        _metric_card('Applicants', _fmt_number(summary['applicants']), f"{_fmt_pct(summary['applicants']/summary['population'] if summary['population'] else None)} of portfolio", styles),
        _metric_card('Default rate', _fmt_pct(summary['default_rate']), f"{_fmt_number(summary['defaults'])} repayment difficulty cases", styles, True),
        _metric_card('Average income', _fmt_compact(summary['average_income']), 'Annual source-currency units', styles),
        _metric_card('Average credit', _fmt_compact(summary['average_credit']), 'Requested credit amount', styles),
        _metric_card('Average age', f"{summary['average_age']:.1f}" if summary['average_age'] is not None else '-', 'Years', styles),
    ]
    story.append(Table([cards], colWidths=[50*mm]*5, hAlign='LEFT', style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),2*mm)])))
    story += [Spacer(1, 7*mm), _paragraph('Portfolio profile', styles['Section'])]
    outcome = Table([
        ['Observed outcome', 'Applicants', 'Share'],
        ['No repayment difficulty', _fmt_number(summary['applicants']-summary['defaults']), _fmt_pct(1-summary['default_rate']) if summary['default_rate'] is not None else '-'],
        ['Repayment difficulty', _fmt_number(summary['defaults']), _fmt_pct(summary['default_rate'])],
    ], colWidths=[62*mm,30*mm,25*mm], rowHeights=9*mm)
    outcome.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),8),('GRID',(0,0),(-1,-1),.5,LINE),('BACKGROUND',(0,1),(-1,-1),colors.white),('ALIGN',(1,1),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),3*mm),('RIGHTPADDING',(0,0),(-1,-1),3*mm)]))
    charts = Table([[[_paragraph('Observed repayment outcomes', styles['Section']), outcome], [_paragraph('Default rate across age groups', styles['Section']), _vertical_chart(summary['age'], height=100)]]], colWidths=[122*mm,132*mm], style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(0,-1),6*mm),('RIGHTPADDING',(1,0),(1,-1),0)]))
    story += [charts, Spacer(1, 3*mm), _paragraph('Debt burden and repayment', styles['Section']), _horizontal_chart(summary['debt'], width=740, height=70), Spacer(1, 1*mm), _paragraph('Rates are descriptive associations within the selected historical cohort. TARGET represents observed repayment difficulty, not a new model prediction.', styles['Body']), PageBreak()]
    story += [_paragraph('Segment detail', styles['Title']), _paragraph(filter_text, styles['Subtitle']), Spacer(1, 5*mm)]
    income_table = [['Income type','Applicants','Cases','Rate']] + [[r['group'],_fmt_number(r['applicants']),_fmt_number(r['defaults']),_fmt_pct(r['rate'],1)] for r in summary['income']]
    education_table = [['Education','Applicants','Cases','Rate']] + [[r['group'],_fmt_number(r['applicants']),_fmt_number(r['defaults']),_fmt_pct(r['rate'],1)] for r in summary['education']]
    def styled_table(rows, widths):
        table=Table(rows,colWidths=widths,repeatRows=1,rowHeights=6.5*mm)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),7),('GRID',(0,0),(-1,-1),.4,LINE),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,BG]),('ALIGN',(1,1),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),2.5*mm),('RIGHTPADDING',(0,0),(-1,-1),2.5*mm)]))
        return table
    detail = Table([[[_paragraph('Income profile', styles['Section']), styled_table(income_table,[47*mm,25*mm,22*mm,20*mm])], [_paragraph('Education profile', styles['Section']), styled_table(education_table,[55*mm,25*mm,22*mm,20*mm])]]], colWidths=[126*mm,132*mm], style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(0,-1),6*mm),('RIGHTPADDING',(1,0),(1,-1),0)]))
    source = str(summary['source']).replace('·', '-').replace('–', '-')
    story += [detail, Spacer(1,3*mm), _paragraph('Age and income concentration', styles['Section']), _matrix(summary['matrix'],styles), Spacer(1,2*mm), _paragraph(f"Source: {source}. This report contains aggregate cohort statistics. It does not include applicant-level records and is intended for research use, not lending decisions.", styles['Body'])]

    def page(canvas, document):
        canvas.saveState()
        canvas.setFillColor(BG)
        canvas.rect(0,0,page_width,page_height,fill=1,stroke=0)
        canvas.setFillColor(TEAL)
        canvas.rect(0,page_height-7*mm,page_width,7*mm,fill=1,stroke=0)
        canvas.setStrokeColor(LINE)
        canvas.line(16*mm,11*mm,page_width-16*mm,11*mm)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica',6.5)
        canvas.drawString(16*mm,7*mm,'CreditScope - dashboard report')
        canvas.drawRightString(page_width-16*mm,7*mm,f'Page {document.page}')
        canvas.restoreState()
    doc.build(story,onFirstPage=page,onLaterPages=page)
    return buffer.getvalue()
