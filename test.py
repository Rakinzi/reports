# Save this code to a file named `generate_presentation.py` and run `python generate_presentation.py`
# Dependencies: pip install python-pptx

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

def build_deck():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    # Palette
    NAVY = RGBColor(0, 51, 102)
    BLUE = RGBColor(0, 102, 204)
    DARK = RGBColor(34, 34, 34)
    WHITE = RGBColor(255, 255, 255)
    CARD_BG = RGBColor(238, 242, 246)
    
    blank_layout = prs.slide_layouts[6]
    
    def add_header(slide, title_text, category_text="STANDARD BANK ZIMBABWE | COUNTRY STRATEGY"):
        header = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.1))
        header.fill.solid()
        header.fill.fore_color.rgb = NAVY
        header.line.fill.background()
        
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.12), Inches(11.7), Inches(0.3))
        p_cat = cat_box.text_frame.paragraphs[0]
        p_cat.text = category_text.upper()
        p_cat.font.size = Pt(10)
        p_cat.font.bold = True
        p_cat.font.color.rgb = RGBColor(180, 210, 245)
        
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.6))
        p_title = title_box.text_frame.paragraphs[0]
        p_title.text = title_text
        p_title.font.size = Pt(22)
        p_title.font.bold = True
        p_title.font.color.rgb = WHITE

    def add_card(slide, left, top, width, height, title, body_paragraphs, bg_color=CARD_BG, border_color=BLUE):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        card.line.color.rgb = border_color
        card.line.width = Pt(1.5)
        
        tf = card.text_frame
        tf.word_wrap = True
        tf.margin_left, tf.margin_right = Inches(0.2), Inches(0.2)
        tf.margin_top, tf.margin_bottom = Inches(0.2), Inches(0.2)
        
        p_head = tf.paragraphs[0]
        p_head.text = title
        p_head.font.size = Pt(15)
        p_head.font.bold = True
        p_head.font.color.rgb = NAVY
        p_head.space_after = Pt(8)
        
        for body in body_paragraphs:
            p = tf.add_paragraph()
            p.text = body
            p.font.size = Pt(12)
            p.font.color.rgb = DARK
            p.space_after = Pt(5)

    # -------------------------------------------------------------
    # SLIDE 1: Title Slide
    # -------------------------------------------------------------
    s1 = prs.slides.add_slide(blank_layout)
    bg1 = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = NAVY
    bg1.line.fill.background()
    
    tb1 = s1.shapes.add_textbox(Inches(1.0), Inches(2.2), Inches(11.333), Inches(3.5))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    
    p = tf1.paragraphs[0]
    p.text = "BRAND STRENGTH AS A DRIVER OF SUSTAINABLE GROWTH"
    p.font.size = Pt(30)
    p.font.bold = True
    p.font.color.rgb = WHITE
    p.space_after = Pt(12)
    
    p2 = tf1.add_paragraph()
    p2.text = "Strategic Proposal to Close the Personal & Private Banking (PPB) Consideration Gap[cite: 1]"
    p2.font.size = Pt(18)
    p2.font.color.rgb = RGBColor(180, 210, 245)
    p2.space_after = Pt(28)
    
    p3 = tf1.add_paragraph()
    p3.text = "Prepared for Group Marketing (South Africa) & Country Executive Leadership\nPresented by Creative Agency Partner (Dicomm McCann) | September 2026"
    p3.font.size = Pt(13)
    p3.font.color.rgb = RGBColor(220, 230, 242)

    # -------------------------------------------------------------
    # SLIDE 2: Executive Summary
    # -------------------------------------------------------------
    s2 = prs.slides.add_slide(blank_layout)
    add_header(s2, "Executive Summary: The Zimbabwe Brand Strength Paradox")
    add_card(s2, 0.8, 1.5, 3.6, 5.2, "R47.5 Billion", [
        "Group Brand Value: Standard Bank remains Africa's most valuable financial services brand[cite: 1].",
        "Strong B2B Anchor: Unmatched institutional credibility in Corporate Banking[cite: 1]."
    ])
    add_card(s2, 4.8, 1.5, 3.6, 5.2, "Score: 76.1 / AA", [
        "Zimbabwe Brand Strength: Ranks #9 across Group markets (AA Balanced Rating)[cite: 1].",
        "High Trust & Safety: Brand equity punches well above financial weight[cite: 1]."
    ])
    add_card(s2, 8.8, 1.5, 3.7, 5.2, "R573 Million", [
        "Brand Value Rank #13: Contributes 1.2% to Group Brand Value & 2.0% to Revenue[cite: 1].",
        "The Consideration Gap: Brand Strength ranks 4 places ahead of Brand Value, revealing a retail conversion bottleneck[cite: 1]."
    ])

    # -------------------------------------------------------------
    # SLIDE 3: Macro Context & Sector Overview
    # -------------------------------------------------------------
    s3 = prs.slides.add_slide(blank_layout)
    add_header(s3, "Zimbabwe Market Context & Banking Sector Overview")
    add_card(s3, 0.8, 1.5, 3.6, 5.2, "Macro Dynamics", [
        "Population: ~16.8M (32% Urban / 68% Rural).",
        "Dual Currency: Operating in USD and ZiG environment.",
        "Informalization: Heavy cash reliance and mobile transaction flows."
    ])
    add_card(s3, 4.8, 1.5, 3.6, 5.2, "Sector Structure", [
        "18 Operating Financial Institutions[cite: 2].",
        "Market Dominance: CBZ Bank leads deposits (~38%) and state business[cite: 1, 2].",
        "Stanbic Holding: Holds ~25% deposit share, led by corporate clients[cite: 1, 2]."
    ])
    add_card(s3, 8.8, 1.5, 3.7, 5.2, "Retail Realities", [
        "Retail Players: FBC, CABS, and EcoCash lead everyday visibility[cite: 1, 2].",
        "Strategic Opportunity: Closing the retail consideration gap to convert awareness into main-bank accounts[cite: 1]."
    ])

    # -------------------------------------------------------------
    # SLIDE 4: Segment Breakdown
    # -------------------------------------------------------------
    s4 = prs.slides.add_slide(blank_layout)
    add_header(s4, "Segment Breakdown: Where the Brand Works vs. Where It Lags")
    add_card(s4, 0.8, 1.5, 3.6, 5.2, "CIB (Corporate) — #1", [
        "BSC Score: ~86.5–87.5[cite: 1]",
        "Flawless Execution: Primary financial partner for multinationals, mining leaders, and NGOs[cite: 1].",
        "Safe Haven: Unrivaled trust for corporate treasury management[cite: 1]."
    ])
    add_card(s4, 4.8, 1.5, 3.6, 5.2, "BCB (Business) — #2", [
        "BSC Score: 77.4[cite: 1]",
        "Solid Positioning: Preferred partner for structured SMEs[cite: 1].",
        "Market Position: Second behind market-leader CBZ (84.4 BSC)[cite: 1]."
    ])
    add_card(s4, 8.8, 1.5, 3.7, 5.2, "PPB (Personal) — #3", [
        "BSC Score: 74.8[cite: 1]",
        "Conversion Bottleneck: High top-of-mind awareness, but lower consideration and emotional warmth[cite: 1].",
        "Trails Local Leaders: Ranks behind CBZ (82.7) and FBC (75.5) in retail equity[cite: 1]."
    ])

    # -------------------------------------------------------------
    # SLIDE 5: Unpacking Brand Strength Drivers
    # -------------------------------------------------------------
    s5 = prs.slides.add_slide(blank_layout)
    add_header(s5, "Unpacking Brand Strength Drivers (Perceptions vs. Behaviours)")
    add_card(s5, 0.8, 1.5, 5.6, 5.2, "Brand Perceptions (Inputs)", [
        "Knowledge: High top-of-mind awareness, but limited awareness of specific personal banking products[cite: 1].",
        "Credibility: #1 in institutional security and financial stability[cite: 1].",
        "Appeal (Deficit): Perceived as distant, corporate, and exclusive rather than warm and local[cite: 1]."
    ])
    add_card(s5, 6.8, 1.5, 5.7, 5.2, "Customer Behaviours (Outputs)", [
        "Selection / Consideration: Low warmth depresses daily account consideration[cite: 1].",
        "Advocacy: High B2B NPS; passive retail advocacy[cite: 1].",
        "Price Acceptance: High tolerance for corporate fees, but friction on retail transaction charges[cite: 1]."
    ])

    # -------------------------------------------------------------
    # SLIDE 6: Target Persona
    # -------------------------------------------------------------
    s6 = prs.slides.add_slide(blank_layout)
    add_header(s6, "Target Persona: Urban Emerging Professionals & Entrepreneurs")
    add_card(s6, 0.8, 1.5, 5.6, 5.2, "Profile & Demographics", [
        "Target Group: Urban Professionals, Tech Founders, NGO Managers & SME Leaders (Ages 25–45).",
        "Income Structure: Stable USD or mixed-currency revenue; receiving cross-border remittances.",
        "Financial Needs: Frictionless digital banking, multi-currency credit/debit cards, seamless global e-commerce."
    ])
    add_card(s6, 6.8, 1.5, 5.7, 5.2, "Strategic Commercial Value", [
        "High Margin Yield: Delivers strong Net Interest Margins (NIM) and FX transaction fee revenue.",
        "Product Cross-Sell: High conversion into asset management, credit card utilization, and private wealth banking.",
        "Lifetime Migration: Serves as the pipeline for long-term private wealth accumulation."
    ])

    # -------------------------------------------------------------
    # SLIDE 7: 3-Year Social Media Performance Audit
    # -------------------------------------------------------------
    s7 = prs.slides.add_slide(blank_layout)
    add_header(s7, "3-Year Social Media Performance Audit (2024–2026 Sector Benchmarks)")
    add_card(s7, 0.8, 1.5, 3.6, 5.2, "Stanbic's Shift", [
        "2024: Ranked #1[cite: 2]",
        "2025: Ranked #2[cite: 2]",
        "2026: Slid to #5[cite: 2]",
        "Cause: Over-reliance on boosted ads, flyer spam, and influencer positioning gap[cite: 2]."
    ])
    add_card(s7, 4.8, 1.5, 3.6, 5.2, "Sector Trends", [
        "Quality > Quantity: High post volume without distinct value depresses engagement[cite: 2].",
        "Paid vs Organic: Sponsored ads build temporary reach but fail to create long-term loyalty[cite: 2]."
    ])
    add_card(s7, 8.8, 1.5, 3.7, 5.2, "Market Winners", [
        "#1 CBZ: Dominated B2B deal storytelling & employee culture[cite: 2].",
        "#2 FBC: Masterclass in event marketing & clean design[cite: 2].",
        "#3 TN Cybertech: Climbed from #14 using a lean 1 post/week model[cite: 2]."
    ])

    # -------------------------------------------------------------
    # SLIDE 8: 15-Bank Ranking Table
    # -------------------------------------------------------------
    s8 = prs.slides.add_slide(blank_layout)
    add_header(s8, "3-Year Banking Social Media Leaderboard (2024–2026)")
    
    t_shape8 = s8.shapes.add_table(16, 4, Inches(0.8), Inches(1.3), Inches(11.7), Inches(5.8))
    t8 = t_shape8.table
    
    headers8 = ["Institution", "2024 Rank", "2025 Rank", "2026 Rank & Summary"]
    data8 = [
        ["CBZ Bank", "2nd", "3rd (tied)", "1st — Consistent giant; dominates B2B narrative[cite: 2]"],
        ["FBC Holdings", "3rd", "1st", "2nd — Event marketing benchmark; clean design[cite: 2]"],
        ["TN Cybertech (Steward)", "8th", "14th", "3rd — Surged via lean 1-post/week model[cite: 2]"],
        ["CABS Zimbabwe", "7th", "5th", "4th — Steady climb; loyal audience engagement[cite: 2]"],
        ["Stanbic Bank Zim", "1st", "2nd", "5th — Hurt by ad fatigue & generic flyers[cite: 2]"],
        ["Ecobank Zimbabwe", "N/T", "N/T", "6th — Strong debut; LinkedIn thought leadership[cite: 2]"],
        ["BancABC Zimbabwe", "9th", "6th (tied)", "7th — Balanced volume with podcasts & TikTok[cite: 2]"],
        ["NBS", "N/T", "10th", "8th — Owns housing niche; volume trap on FB[cite: 2]"],
        ["ZB Financial Holdings", "4th", "6th (tied)", "9th — Slide due to sales-heavy flyers[cite: 2]"],
        ["First Capital Bank", "6th", "9th", "10th — Profit growth undone by lifeless feeds[cite: 2]"],
        ["Nedbank Zimbabwe", "N/T", "3rd (tied)", "11th — Sports brilliance undone by static graphics[cite: 2]"],
        ["NMB Bank (NMBZ)", "5th", "8th", "12th — Steep fall into corporate notice board[cite: 2]"],
        ["AFC Commercial Bank", "10th", "11th", "13th — TikTok experiments; core channels weak[cite: 2]"],
        ["Empowerbank", "11th", "13th", "14th — Improved design; formal corporate voice[cite: 2]"],
        ["POSB Zimbabwe", "N/T", "12th", "15th — Physical giant dormant on digital channels[cite: 2]"]
    ]
    
    for c, h in enumerate(headers8):
        cell = t8.cell(0, c)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        for p in cell.text_frame.paragraphs:
            p.font.bold = True
            p.font.size = Pt(10.5)
            p.font.color.rgb = WHITE
            
    for r, row in enumerate(data8):
        for c, val in enumerate(row):
            cell = t8.cell(r + 1, c)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = CARD_BG if r % 2 == 0 else WHITE
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(9)
                p.font.color.rgb = DARK

    # -------------------------------------------------------------
    # SLIDE 9: Bank-by-Bank Takeaways
    # -------------------------------------------------------------
    s9 = prs.slides.add_slide(blank_layout)
    add_header(s9, "Bank-by-Bank Summary & Key Takeaways (Pages 11–18)")
    add_card(s9, 0.8, 1.5, 3.6, 5.2, "The Leaders", [
        "CBZ (#1): Owns LinkedIn deal flow; needs automated lead routing on Facebook[cite: 2].",
        "FBC (#2): Quality over quantity champion; needs TikTok entry for youth[cite: 2].",
        "TN Cybertech (#3): Turnaround hero; proves 1 high-value post/wk beats spam[cite: 2]."
    ])
    add_card(s9, 4.8, 1.5, 3.6, 5.2, "Stanbic Focus (#5)", [
        "Creative Edge: Top-tier video production (Polo Reels)[cite: 2].",
        "Strategic Mismatch: Comedic creators clash with corporate positioning[cite: 2].",
        "Action: Recalibrate creator deals to match aspirational retail identity[cite: 2]."
    ])
    add_card(s9, 8.8, 1.5, 3.7, 5.2, "Peer Lessons", [
        "FCB (#10) & NMB (#12): Strong financial statements mean nothing if social feeds are static notice boards[cite: 2].",
        "Ecobank (#6): Untapped music festival assets[cite: 2].",
        "Nedbank (#11): Lost ranking after dropping dynamic sports reels[cite: 2]."
    ])

    # -------------------------------------------------------------
    # SLIDE 10: Digital Operational Directives
    # -------------------------------------------------------------
    s10 = prs.slides.add_slide(blank_layout)
    add_header(s10, "Digital & Social Media Operational Directives")
    add_card(s10, 0.8, 1.5, 5.6, 5.2, "Operational Imperatives", [
        "1. Insource Daily Community Desks: Reserve external agencies for 360 strategy & media buying[cite: 2].",
        "2. Enforce Platform Roles: Stop uniform cross-posting across LinkedIn, Facebook, Instagram, and TikTok[cite: 2].",
        "3. Protect Customer Privacy: Deploy automated tools to hide client emails dropped in open threads[cite: 2]."
    ])
    add_card(s10, 6.8, 1.5, 5.7, 5.2, "Content & Analytics Shifts", [
        "4. Transition to Edutainment: Replace static product flyers with human stories and reels[cite: 2].",
        "5. Own Distinct USPs: Stop publishing identical product menus; claim unique territory[cite: 2].",
        "6. Measure Full-Funnel KPIs: Track CAC, CLV, and conversion rather than vanity likes[cite: 2]."
    ])

    # -------------------------------------------------------------
    # SLIDE 11: Campaign Messaging Matrix
    # -------------------------------------------------------------
    s11 = prs.slides.add_slide(blank_layout)
    add_header(s11, "Campaign Messaging Matrix: From Corporate Distance to Human Growth")
    add_card(s11, 0.8, 1.5, 5.6, 5.2, "Current Perception -> Campaign Position", [
        "Brand Identity: 'Elite corporate bank' -> 'A partner fueling personal ambition.'",
        "Onboarding: 'Cumbersome paperwork' -> 'Instant, 3-minute digital access.'",
        "Card Access: 'Strict requirements' -> 'Global purchasing power in your hand.'"
    ])
    add_card(s11, 6.8, 1.5, 5.7, 5.2, "Executional Copy Examples", [
        "Identity: 'You don't need to be a corporation to bank like one.'",
        "Onboarding: 'Open your account before your morning coffee cools down.'",
        "Connection: 'Driven by Zimbabwe's hustle. Backed by Africa's biggest bank.'"
    ])

    # -------------------------------------------------------------
    # SLIDE 12: Technology Engine (AI Integration)
    # -------------------------------------------------------------
    s12 = prs.slides.add_slide(blank_layout)
    add_header(s12, "Technology Engine: Scaling Personalization via AI Workflows")
    add_card(s12, 0.8, 1.5, 5.6, 5.2, "Content & Onboarding AI", [
        "1. AI Personalization Engine: Dynamic ad copy generation in Shona, Ndebele, and English.",
        "2. WhatsApp Onboarding Agent: Instant KYC pre-screening and account creation via WhatsApp."
    ])
    add_card(s12, 6.8, 1.5, 5.7, 5.2, "Analytics & Nurturing AI", [
        "3. Predictive Lead Nurturing: Machine learning analyzing transaction triggers for cross-selling.",
        "4. AI Social Listening: Real-time sentiment tracking and automated customer dispute routing."
    ])

    # -------------------------------------------------------------
    # SLIDE 13: 8-Bank Competitive Matrix
    # -------------------------------------------------------------
    s13 = prs.slides.add_slide(blank_layout)
    add_header(s13, "Comprehensive Competitive Matrix — Stanbic vs. Peer Group (8 Banks)")
    
    t_shape13 = s13.shapes.add_table(9, 4, Inches(0.8), Inches(1.3), Inches(11.7), Inches(5.8))
    t13 = t_shape13.table
    
    headers13 = ["Institution", "Brand Strength Index", "Social Media Audit (Mukondo)", "Financial & Market Share Position"]
    data13 = [
        ["Stanbic Bank Zim", "BSC: 76.1 (AA)[cite: 1] | PPB #3 (74.8)[cite: 1]", "2024 #1 -> 2026 #5; Ad fatigue[cite: 2]", "Deposit Share: ~25%[cite: 1, 2] | Net Income Leader"],
        ["CBZ Bank", "BSC: 82.7 (#1 PPB)[cite: 1]", "2024 #2 -> 2026 #1; B2B deal focus[cite: 2]", "Deposit Share: ~38%[cite: 1, 2] | Systemic Market Giant"],
        ["FBC Holdings", "BSC: 75.5 (#2 PPB)[cite: 1]", "2024 #3 -> 2026 #2; Quality > Quantity[cite: 2]", "Deposit Share: ~19%[cite: 1, 2] | Strong Local Resonance"],
        ["TN Cybertech", "Rebrand turnaround", "2024 #8 -> 2026 #3; Lean 1 post/wk[cite: 2]", "EcoCash / Digital ecosystem integration"],
        ["CABS Zimbabwe", "Trusted mortgage heritage", "2024 #7 -> 2026 #4; CSR & giveaways[cite: 2]", "Housing loans & deep retail client balance sheet"],
        ["First Capital Bank", "Strong balance sheet vs brand", "2024 #6 -> 2026 #10; Lifeless feeds[cite: 2]", "Deposit Share: ~6% | Highly profitable USD lending"],
        ["ZB Financial", "Middle-tier BSC", "2024 #4 -> 2026 #9; Sales flyer spam[cite: 2]", "Deposit Share: ~12% | Heavy promotional flyers"],
        ["Nedbank Zimbabwe", "High governance score", "2024 N/T -> 2026 #11; Sporting fatigue[cite: 2]", "Total Assets: ZWG 6.35bn | Tier-2 Corporate/Private"]
    ]
    
    for c, h in enumerate(headers13):
        cell = t13.cell(0, c)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        for p in cell.text_frame.paragraphs:
            p.font.bold = True
            p.font.size = Pt(10.5)
            p.font.color.rgb = WHITE
            
    for r, row in enumerate(data13):
        for c, val in enumerate(row):
            cell = t13.cell(r + 1, c)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = CARD_BG if r % 2 == 0 else WHITE
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(9)
                p.font.color.rgb = DARK

    # -------------------------------------------------------------
    # SLIDE 14: Global Benchmarks
    # -------------------------------------------------------------
    s14 = prs.slides.add_slide(blank_layout)
    add_header(s14, "Global Benchmarks: Learning from International Leaders")
    add_card(s14, 0.8, 1.5, 3.6, 5.2, "DBS Bank (Singapore)", [
        "Strategy: 'Make Banking Joyful'.",
        "Execution: Embedded banking directly into lifestyle apps, removed friction, and converted trust into daily usage.",
        "Takeaway: Make retail banking invisible yet essential."
    ])
    add_card(s14, 4.8, 1.5, 3.6, 5.2, "Revolut / Barclays (UK)", [
        "Strategy: Multi-Currency & Accessibility.",
        "Execution: Instant FX onboarding, sleek card UI, paired with human-centric community marketing.",
        "Takeaway: Simplify multi-currency onboarding."
    ])
    add_card(s14, 8.8, 1.5, 3.7, 5.2, "Capital One (USA)", [
        "Strategy: Emotional Relatability.",
        "Execution: Replaced traditional corporate ads with consumer-centric campaigns focused on lifestyle rewards.",
        "Takeaway: Move away from rigid boardroom imagery."
    ])

    # -------------------------------------------------------------
    # SLIDE 15: Strategic Recommendations
    # -------------------------------------------------------------
    s15 = prs.slides.add_slide(blank_layout)
    add_header(s15, "Actionable Strategic Recommendations & Execution Plan")
    add_card(s15, 0.8, 1.5, 5.6, 5.2, "Execution Pillars 1 & 2", [
        "1. Reposition & Humanize Brand: Shift campaign tone from corporate authority to relatable personal progress.",
        "2. Zero-Friction Onboarding: Launch WhatsApp & mobile-web instant account opening with 3-minute completion."
    ])
    add_card(s15, 6.8, 1.5, 5.7, 5.2, "Execution Pillars 3 & 4", [
        "3. Tailored Value Propositions: Package USD card & savings suites for urban professionals.",
        "4. Group & Country Alignment: Flex Group guidelines to give country marketing agility in local campaigns[cite: 1]."
    ])

    # -------------------------------------------------------------
    # SLIDE 16: Funnel Governance & Target Roadmap
    # -------------------------------------------------------------
    s16 = prs.slides.add_slide(blank_layout)
    add_header(s16, "Governance, KPIs & Measurement Roadmap")
    add_card(s16, 0.8, 1.5, 5.6, 5.2, "12-Month Performance Targets", [
        "Retail Consideration (PPB): Increase score from 74.8 to 80.0+ BSC[cite: 1].",
        "Digital Account Openings: Achieve +45% growth in monthly digital activations.",
        "Main-Bank Status: Convert +25% of secondary retail account holders.",
        "Revenue Contribution: Boost retail fee & FX contribution to country earnings."
    ])
    add_card(s16, 6.8, 1.5, 5.7, 5.2, "Immediate Next Steps", [
        "Month 1: Present proposal to Group Marketing (SA) and secure alignment.",
        "Month 2: Finalize campaign creative and configure WhatsApp AI onboarding engine.",
        "Month 3: Launch refreshed Personal & Private Banking campaign across channels."
    ])

    prs.save("Standard_Bank_Zimbabwe_Strategy_Deck.pptx")
    print("Presentation generated successfully: Standard_Bank_Zimbabwe_Strategy_Deck.pptx")

if __name__ == "__main__":
    build_deck()
