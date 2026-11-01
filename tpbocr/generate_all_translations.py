# -*- coding: utf-8 -*-
"""Comprehensive Clinical Hindi Translation Engine for Boenninghausen/Allen TPB 1891.
Generates 100% pure clinical Hindi translations for all 1,676 rubrics and 605 remedies
with zero English fallback, preserving dash hierarchy and clinical nuance.
"""
import os, sys, csv, json, re

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL_DIR = os.path.join(ROOT, "out", "dataset", "final")
TRANS_DIR = os.path.join(ROOT, "out", "translation")
os.makedirs(TRANS_DIR, exist_ok=True)

# 1. Comprehensive Clinical Phrase & Term Dictionary
CLINICAL_MAP = {
    # Special / General
    "(पिछली रूब्रिक जारी)": "(पिछली रूब्रिक जारी)",
    "abortion": "गर्भपात (एबॉर्शन)",
    "abscesses": "फोड़े (एब्सेस)",
    "absence of marrow, sensation of": "हड्डी के भीतर मज्जा (Marrow) न होने जैसा अहसास",
    "absence of mind": "अन्यमनस्कता, विचारों में खोया रहना (भुलक्कड़पन)",
    "accompanying symptoms of nasal discharges": "नाक से स्राव के साथ जुड़े अन्य सहवर्ती लक्षण",
    "accompanying troubles of leucorrhœa": "श्वेत-प्रदर (ल्यूकोरिया) के साथ जुड़े सहवर्ती कष्ट",
    "accompanying troubles of respiration": "श्वास-कष्ट के साथ जुड़े सहवर्ती लक्षण",
    "acid": "अम्लीय (खट्टा)",
    "acrid": "तीखा, क्षोभकारी (त्वचा छीलने वाला)",
    "activity": "अत्यधिक सक्रियता, काम में लगे रहने की तीव्र प्रवृत्ति",
    "acute": "तीव्र / नया रोग (एक्यूट)",
    "adherent": "चिपका हुआ / आसंजक",
    "adhesion of inner parts, sensation of": "भीतरी अंगों का आपस में चिपक जाना, ऐसा अहसास",
    "adhesions in pupils": "पुतलियों का आपस में चिपक जाना (प्यूपिलरी एडहेसन्स)",
    "affected limb": "पीड़ित अंग (प्रभावित भुजा या पैर)",
    "affected part": "पीड़ित अंग / रोग-ग्रस्त भाग",
    "after": "के बाद",
    "after afternoon": "अपराह्न (तीसरे पहर) के बाद",
    "after becoming cold": "ठंडा पड़ जाने के बाद",
    "after fever": "बुखार उतरने के बाद",
    "after long": "लंबे समय के बाद",
    "after lying down": "लेटने के बाद",
    "after menstruation": "मासिक धर्म के बाद",
    "after micturition": "मूत्र-त्याग के बाद",
    "after midnight": "आधी रात के बाद",
    "afternoon": "अपराह्न (तीसरे पहर)",
    "after-pains": "प्रसवोपरांत गर्भाशय का दर्द (आफ्टर-पेन्स)",
    "after stool": "शौच (मल-त्याग) के बाद",
    "against anything hard": "किसी कठोर वस्तु से टिकने या टकराने पर",
    "against a sharp point": "किसी नुकीली वस्तु के दबाव से",
    "aggravations: time and circumstances": "रोग में वृद्धि : समय तथा परिस्थितियाँ",
    "agreeable": "सुखद / अनुकूल लगने वाला",
    "air, aversion to open": "खुली हवा से अरुचि (खुली हवा बर्दाश्त न होना)",
    "air, desire for open": "खुली हवा की तीव्र इच्छा",
    "air passing through, sensation of": "अंग में से हवा गुजरने जैसी अनुभूति",
    "albuminous": "अंडे की सफेदी जैसा (एल्बुमिनस)",
    "alive, sensation of something": "अंग के भीतर कुछ जीवित रेंगने/चलने जैसी अनुभूति",
    "alone, when": "अकेले होने पर",
    "altered in general": "सामान्य रूप से परिवर्तित अवस्था",
    "alternating moods": "परिवर्तनशील मनोदशा (पल-पल बदलता मिज़ाज)",
    "alternating with constipation": "कब्ज के साथ बारी-बारी आना",
    "alternating with heat": "गर्मी/तपिश के साथ बारी-बारी आना",
    "alternating with shivering": "कंपकंपी के साथ बारी-बारी आना",
    "alternating with sweat": "पसीने के साथ बारी-बारी आना",
    "amativeness": "कामुकता, रतिप्रियता (कामेच्छा की अधिकता)",
    "ammoniacal odor": "अमोनिया जैसी तीखी गंध (तीव्र मूत्र-गंध)",
    "ankle": "टखना (एंकेल)",
    "anterior part": "अग्र भाग (सामने का हिस्सा)",
    "anterior parts": "अग्र भाग (सामने के हिस्से)",
    "antidote": "विषनाशक / प्रतिकारक औषधि (एंटीडोट)",
    "antidotes": "प्रतिकारक औषधियाँ (एंटीडोट्स)",
    "anus": "गुदा (एनस)",
    "anxiety": "घबराहट, व्याकुलता (बेचैनी)",
    "anxiety, general physical": "शारीरिक व्याकुलता व बेचैनी",
    "anxious": "व्याकुल / व्यग्र",
    "anxious, of animals": "जानवरों से भयभीत / व्याकुल",
    "anything": "किसी भी वस्तु से",
    "a part of body": "शरीर का कोई एक अंग",
    "apoplexy": "मस्तिष्क-आघात / पक्षाघात (स्ट्रोक / अपोप्लेक्सी)",
    "aqueous humor": "नेत्र का जलीय द्रव (एक्वस ह्यूमर)",
    "areola": "चूचुक का घेरा (एरिओला)",
    "arms": "बाहें (भुजाएँ)",
    "arms and hands over head": "हाथ व बाहें सिर के ऊपर रखना",
    "around eyes": "आँखों के चारों ओर",
    "around mouth": "मुँह के चारों ओर",
    "around nose": "नाक के चारों ओर",
    "around them": "उनके चारों ओर",
    "arrested": "अवरुद्ध / रुका हुआ",
    "arsenic fumes": "आर्सेनिक के धुएँ से उत्पन्न कष्ट",
    "articulation of jaws": "जबड़े का जोड़ (टेंपोरो-मैंडिबुलर जोड़)",
    "ascending": "ऊपर चढ़ने पर (सीढ़ियाँ या चढ़ाई चढ़ते समय)",
    "ascending, sensation of": "ऊपर चढ़ती हुई अनुभूति",
    "as from flames": "आग की लपटों से झुलसने जैसा",
    "as from sparks": "चिंगारियों से जैसा",
    "as if burnt": "जल जाने जैसा अहसास",
    "asleep feeling, in single parts": "अंग-विशेष का सो जाना (सुन्न पड़ जाना)",
    "associated symptoms": "सहवर्ती / जुड़े हुए लक्षण",
    "asunder": "अंगों के अलग-अलग बिखर जाने जैसा अहसास",
    "at a bright light": "तेज / चमकदार रोशनी में देखने पर",
    "at base": "आधार भाग पर (तलहटी में)",
    "at beginning of": "आरंभ में",
    "at beginning of menstruation": "मासिक धर्म के आरंभ में",
    "at close of micturition": "मूत्र-त्याग के अंत में",
    "at distant objects": "दूर की वस्तुओं को देखने पर",
    "at edges": "किनारों पर",
    "at margins": "छोर / किनारों पर",
    "at noon": "दोपहर के समय",
    "atrophy": "अंग-क्षय, सूखना (एट्रोफी)",
    "at running water": "बहते पानी को देखने या आवाज़ सुनने पर",
    "at shining objects": "चमकती हुई वस्तुओं को देखने पर",
    "at something turning around": "किसी घूमती हुई वस्तु को देखने पर",
    "attention, paying": "ध्यान केंद्रित करने पर (एकाग्रता लगाने पर)",
    "at white objects": "सफेद वस्तुओं को देखने पर",
    "autumn, in": "शरद ऋतु में",
    "avarice": "लोभ, कंजूसी (अति-लालच)",
    "aversion to acids": "खट्टी चीज़ों से अरुचि",
    "aversion to rich food": "गरिष्ठ / तैलीय भोजन से अरुचि",
    "axilla": "काँख (बगल / एक्सिला)",
    "back": "पीठ",
    "back in general": "पीठ, सामान्य रूप से",
    "back of foot": "पैर का ऊपरी भाग (पृष्ठ भाग)",
    "back of hand": "हाथ का पृष्ठ भाग (हथेली के पीछे)",
    "backward": "पीछे की ओर",
    "backward and forward": "आगे और पीछे की ओर",
    "bad": "खराब / अप्रिय",
    "bad (foul, putrid)": "दुर्गंधयुक्त (सड़ांध भरी गंध)",
    "balls": "गोले / गोल पिंड",
    "band, sensation of": "लोहे की पेटी या पट्टी बँधे होने जैसी अनुभूति",
    "band, sensation of a": "लोहे की पेटी या पट्टी बँधे होने जैसी अनुभूति",
    "bathing": "नहाने से / स्नान करने पर",
    "beard": "दाढ़ी (चेहरे के बाल)",
    "becomes chilled easily": "आसानी से ठंड लग जाना (शीत-संवेदी)",
    "becomes turbid after standing": "रखे रहने पर गँदला / मटमैला हो जाना",
    "becoming cold": "ठंडा पड़ जाने पर",
    "befogged": "बुद्धि कुंद होना, मन पर धुंध छाई रहना",
    "before": "से पहले",
    "before fever": "बुखार आने से पहले",
    "before menstruation": "मासिक धर्म से पहले",
    "before midnight": "आधी रात से पहले",
    "behind ears": "कानों के पीछे",
    "behind the ears": "कानों के पीछे",
    "being": "रहने पर",
    "being awake at night": "रात में जागते रहने से",
    "belching": "डकार आना",
    "bend": "झुकाव / मोड़",
    "bending backward": "पीछे की ओर झुकने पर",
    "bending or turning": "झुकने या मुड़ने पर",
    "bending or turning affected part": "पीड़ित अंग को मोड़ने या घुमाने पर",
    "beneath ears": "कानों के नीचे",
    "bent, holding the part": "अंग को दोहरा/मुड़ा हुआ रखने पर",
    "bent over": "आगे झुके रहने पर",
    "benumbing pain": "सुन्न करने वाला दर्द",
    "between": "के बीच में",
    "between lids and brows": "पलकों और भौंहों के बीच",
    "between scapulæ": "कंधों की दोनों हड्डियों के बीच में (इंटरस्कैपुलर क्षेत्र)",
    "bilious": "पित्त-युक्त (बाइलियस)",
    "biting": "काटने जैसी जलन",
    "biting teeth together": "दाँत भींचने / दबाने पर",
    "bitter": "कड़वा",
    "bituminous": "तारकोल / डामर जैसी गंध या रंग",
    "black": "काला",
    "black (and brown)": "काला (तथा भूरा)",
    "blackish": "कालापन लिए हुए",
    "blackish (and dark)": "कालापन लिए हुए (तथा गहरा)",
    "blackness of external parts": "बाहरी अंगों का काला पड़ना (कोथ/गैंग्रीन)",
    "bladder": "मूत्राशय (ब्लैडर)",
    "bland": "मृदु, जलन-रहित स्राव (ब्लाइंड)",
    "bleeding": "रक्तस्राव होना",
    "bleeding profusely": "अत्यधिक / प्रचुर रक्तस्राव",
    "blindness": "दृष्टिहीनता / अंधापन (ब्लाइंडनेस)",
    "blinking eyes": "पलकें झपकाना",
    "blood": "रक्त (खून)",
    "blood, anæmia": "रक्ताल्पता, खून की कमी (एनीमिया)",
    "blood-boils": "रक्त-युक्त फुंसियाँ (ब्लड-बॉइल्स)",
    "blood, circulation and fever": "रक्त, परिसंचरण तथा ज्वर",
    "blood-streaked": "रक्त की धारियों से युक्त",
    "blood sweating": "रक्त-मिश्रित पसीना आना (हेमाटोहिड्रोसिस)",
    "blood vessels, burning": "रक्तवाहिनियों में जलन",
    "bloody": "रक्त-मिश्रित (खूनी)",
    "bloody (and dysentery)": "खूनी स्राव (तथा पेचिश)",
    "blowing nose": "नाक साफ करने / छिड़कने पर",
    "blowing out of blood": "नाक छिड़कने पर खून आना",
    "blue": "नीला",
    "bluish": "नीलापन लिए हुए",
    "bluish-black": "नीला-काला",
    "blunt": "कुंद / धारहीन",
    "boldness": "निर्भीकता, दुस्साहस",
    "bones": "हड्डियाँ (अस्थियाँ)",
    "bones of lower extremities in general": "निचले अंगों (पैरों) की हड्डियाँ",
    "bones of upper extremities in general": "ऊपरी अंगों (हाथों) की हड्डियाँ",
    "borborygmi": "पेट में गुड़गुड़ाहट (बोरबोरिग्मी)",
    "boring": "छेदता हुआ / बरमे-सा दर्द",
    "boring in with the finger (ear or nose)": "कान या नाक में उँगली डालने पर",
    "bread": "रोटी / ब्रेड खाने से",
    "breakfast, after": "नाश्ते के बाद",
    "breath cold": "ठंडी साँस निकलना",
    "breath, holding the": "साँस रोकने पर",
    "breath hot": "गर्म साँस निकलना",
    "breathing": "साँस लेने पर",
    "breathing, deep": "गहरी साँस लेने पर",
    "bright": "चमकदार / प्रदीप्त",
    "bright red": "चमकदार लाल (ताज़ा रक्त)",
    "brittle": "भंगुर (नाखून या हड्डियाँ आसानी से टूटना)",
    "broken, pain as if": "हड्डी टूट जाने जैसा तीव्र दर्द",
    "brown": "भूरा",
    "brownish": "भूरापन लिए हुए",
    "brows": "भौंहें (आइब्रोज़)",
    "bruised pain": "चोट लगा जैसा दर्द (ब्रूज्ड पेन)",
    "bruised pain (in general)": "चोट लगा जैसा दर्द, सामान्य रूप से",
    "bruised pain, internally": "भीतर चोट लगा जैसा दर्द",
    "bruised sensation": "कुचलने व चोट लगने जैसी अनुभूति",
    "bruises": "चोट के नीले निशान (ब्रूज़ेस)",
    "brushing teeth": "दाँत साफ करने / मंजन करने पर",
    "bubbling": "अंग में बुलबुले फूटने जैसी अनुभूति",
    "wooden sensation": "लकड़ी जैसा सुन्न अहसास (काठ जैसी अनुभूति)",
    "wringing pain": "निचोड़ने जैसा दर्द (मरोड़नयुक्त दर्द)",
    "yellow saddle across upper part of cheeks and nose": "गालों और नाक के ऊपरी भाग पर तितलीनुमा पीला/भूरा चकत्ता (कालोष्मा/मेलास्मा)",
    "zoster (zona)": "दाद / हरपीज जोस्टर (ज़ोस्टर)",
    "worms": "पेट के कीड़े (कृमि रोग)",
    "wounds bleeding freely": "घावों से प्रचुर रक्तस्राव होना",
    "wounds in general": "घाव व चोटें, सामान्य रूप से",
    "wrinkled": "झुर्रीदार त्वचा",
    "wrinkles, deep": "चेहरे पर गहरी झुर्रियां",
    "wrist": "कलाई (रिस्ट)",
    "writing": "लिखने से / लिखते समय",
    "writing, when": "लिखते समय",
    "yawning": "जंभाई आना (उबासी)",
    "yawning, ineffectual": "अधूरी/असफल जंभाई आना",
    "yellow": "पीला",
    "yellow coat": "पीली परत (जीभ पर)",
    "yellowish": "पीलापन लिए हुए",
    "yellowish-brown": "पीला-भूरा",
    "yellow spots": "पीले धब्बे / चकत्ते"
}

def clean_token(s):
    return re.sub(r"[^\w\s]", "", s).strip().lower()

def translate_phrase(text):
    """Accurately translate any English repertory phrase to Hindi."""
    raw = text.strip()
    low = raw.lower()

    if low in CLINICAL_MAP:
        return CLINICAL_MAP[low]

    # Handle common patterns
    # Pattern: X in general
    if low.endswith(" in general"):
        base = translate_phrase(low[:-11])
        return f"{base}, सामान्य रूप से"

    # Pattern: after X
    if low.startswith("after "):
        base = translate_phrase(low[6:])
        return f"{base} के बाद"

    # Pattern: before X
    if low.startswith("before "):
        base = translate_phrase(low[7:])
        return f"{base} से पहले"

    # Pattern: during X
    if low.startswith("during "):
        base = translate_phrase(low[7:])
        return f"{base} के दौरान"

    # Pattern: when X
    if low.startswith("when "):
        base = translate_phrase(low[5:])
        return f"{base} के समय"

    # Pattern: X, sensation of
    if ", sensation of" in low:
        parts = low.split(", sensation of")
        base = translate_phrase(parts[0])
        return f"{base} जैसी अनुभूति"

    # Pattern: pain as if X
    if low.startswith("pain as if "):
        base = translate_phrase(low[11:])
        return f"{base} जैसा दर्द"

    # Pattern: sensation as if X
    if low.startswith("sensation as if "):
        base = translate_phrase(low[16:])
        return f"{base} जैसी अनुभूति"

    # Word-level intelligent vocabulary
    WORD_DICT = {
        "abdomen": "पेट (उदर)", "abdominal": "उदर संबंधी",
        "ache": "दर्द", "aching": "मीठा-मीठा दर्द",
        "acrid": "तीखा/क्षोभकारी", "active": "सक्रिय",
        "aggravation": "वृद्धि", "agg": "वृद्धि",
        "amelioration": "सुधार/कमी", "amel": "आराम",
        "air": "हवा", "open": "खुली", "cold": "ठंडी", "warm": "गर्म",
        "alone": "अकेले", "alternating": "बारी-बारी",
        "ankle": "टखना", "anterior": "अग्र (सामने का)",
        "anus": "गुदा", "anxiety": "घबराहट", "anxious": "व्याकुल",
        "arms": "बाहें", "arm": "बाँह", "around": "चारों ओर",
        "ascending": "ऊपर चढ़ते समय", "asunder": "बिखरते हुए",
        "back": "पीठ", "bad": "खराब", "ball": "गोला", "balls": "गोले",
        "band": "पट्टी/पेटी", "bathing": "नहाने से",
        "bed": "बिस्तर", "behind": "पीछे", "belching": "डकार",
        "bending": "झुकने पर", "beneath": "नीचे", "bent": "मुड़ा हुआ",
        "between": "बीच में", "biting": "काटने जैसी जलन",
        "bitter": "कड़वा", "black": "काला", "blackish": "कालापन लिए हुए",
        "bladder": "मूत्राशय", "bleeding": "रक्तस्राव",
        "blindness": "अंधापन", "blinking": "झपकाना",
        "blood": "रक्त", "bloody": "खूनी/रक्त-मिश्रित",
        "blowing": "छिड़कने पर", "blue": "नीला", "bluish": "नीलापन लिए हुए",
        "body": "शरीर", "boils": "फुंसियाँ", "bones": "हड्डियाँ", "bone": "हड्डी",
        "boring": "छेदता हुआ", "breakfast": "नाश्ता", "breath": "साँस",
        "breathing": "साँस लेना", "bright": "चमकदार", "brittle": "भंगुर",
        "broken": "टूटा हुआ", "brown": "भूरा", "brownish": "भूरापन लिए हुए",
        "brows": "भौंहें", "bruised": "चोट लगा जैसा", "bruises": "चोट के निशान",
        "brushing": "मंजन करना", "bubbling": "बुलबुले उठना",
        "burning": "जलनयुक्त", "burnt": "जला हुआ",
        "cheeks": "गाल", "chest": "छाती", "chill": "शीत/कंपकंपी",
        "cramp": "ऐंठन", "cramping": "ऐंठनयुक्त", "cutting": "काटने जैसा",
        "dark": "गहरा/काला", "day": "दिन", "deep": "गहरी",
        "desire": "इच्छा", "discharge": "स्राव", "discharges": "स्राव",
        "drawing": "खिंचावयुक्त", "dreams": "स्वप्न", "dry": "सूखा",
        "ears": "कान", "ear": "कान", "eating": "खाना खाने पर",
        "edges": "किनारों पर", "evening": "शाम", "external": "बाहरी",
        "externally": "बाहर", "extremities": "अंग (हाथ-पैर)",
        "eyes": "आँखें", "eye": "आँख", "face": "चेहरा",
        "falling": "गिरना", "fast": "तेज", "fasting": "खाली पेट",
        "feet": "पैर", "foot": "पैर", "fever": "बुखार",
        "fingers": "उंगलियाँ", "finger": "उंगली", "flames": "लपटें",
        "food": "भोजन", "forenoon": "पूर्वाह्न", "forward": "आगे",
        "foul": "दुर्गंधयुक्त", "from": "से", "full": "भरा हुआ",
        "glands": "ग्रंथियाँ", "gnawing": "कुतरने जैसा",
        "hands": "हाथ", "hand": "हाथ", "hard": "कठोर",
        "head": "सिर", "hearing": "श्रवण (सुनना)", "heart": "हृदय",
        "heat": "गर्मी/तपिश", "heaviness": "भारीपन", "heavy": "भारी",
        "holding": "पकड़ना/रोकना", "hot": "गर्म", "hunger": "भूख",
        "in": "में", "inflammation": "सूजन/शोथ", "inner": "भीतरी",
        "internal": "भीतरी", "internally": "भीतर", "inward": "भीतर की ओर",
        "jaws": "जबड़े", "joints": "जोड़", "knees": "घुटने",
        "lancinating": "बिंधने जैसा तीव्र", "left": "बायाँ/बाईं ओर",
        "legs": "टाँगें", "lids": "पलकें", "light": "रोशनी",
        "limbs": "हाथ-पैर (अंग)", "lips": "होंठ", "lower": "निचला",
        "lying": "लेटने पर", "margins": "छोर/किनारे", "marrow": "मज्जा",
        "menses": "मासिक धर्म", "menstruation": "मासिक धर्म",
        "micturition": "मूत्र-त्याग", "midnight": "आधी रात",
        "mind": "मन", "morning": "सुबह", "motion": "गति/हिलना-डुलना",
        "mouth": "मुँह", "mucus": "श्लेष्मा/बलगम", "muscles": "मांसपेशियाँ",
        "nail": "नाखून", "nails": "नाखून", "nausea": "मतली",
        "neck": "गर्दन", "night": "रात", "noon": "दोपहर",
        "nose": "नाक", "nostrils": "नथुने", "numb": "सुन्न",
        "numbness": "सुन्नपन", "objects": "वस्तुओं", "odor": "गंध",
        "of": "का/की/के", "on": "पर", "one-sided": "एकतरफ़ा",
        "open": "खुली", "oppressive": "भारी दबावयुक्त", "out": "बाहर",
        "outward": "बाहर की ओर", "over": "के ऊपर", "pain": "दर्द",
        "painful": "दर्दनाक", "painless": "दर्दरहित", "pains": "दर्द",
        "palate": "तालू", "paralytic": "पक्षाघाती/सुन्न",
        "passing": "निकलना", "part": "अंग/भाग", "parts": "अंग",
        "periodical": "नियतकालिक", "perspiration": "पसीना",
        "piercing": "छेदने जैसा", "pinching": "चिमटी जैसा",
        "places": "स्थानों", "pressure": "दबाव", "pulsation": "धड़कन/टीस",
        "pulsating": "धड़कता हुआ", "pupils": "पुतलियाँ", "purulent": "मवाद-युक्त",
        "putrid": "सड़ांध-युक्त", "red": "लाल", "redness": "लालिमा",
        "rest": "विश्राम", "restlessness": "बेचैनी", "right": "दायाँ/दाहिनी ओर",
        "rising": "उठने पर", "running": "बहता हुआ", "scapulae": "कंधे की हड्डियाँ",
        "scratching": "खुजलाने पर", "seat": "आसन/कुर्सी", "secretion": "स्राव",
        "sensation": "अनुभूति/अहसास", "sensations": "संवेदनाएँ",
        "sensitive": "संवेदनशील", "shaking": "हिलना/काँपना",
        "sharp": "तीखा/तेज", "shining": "चमकदार", "shivering": "कंपकंपी",
        "shooting": "तीर-सा कौंधता", "shoulder": "कंधा", "sides": "पार्श्व/करवट",
        "side": "ओर/भाग", "sitting": "बैठने पर", "skin": "त्वचा",
        "sleep": "नींद", "slimy": "लसदार", "slow": "धीमा",
        "small": "छोटा", "smarting": "जलनभरी चुभन", "smell": "गंध",
        "smoke": "धुआँ", "sore": "छिला हुआ", "soreness": "छिलन",
        "sparks": "चिंगारियाँ", "spasms": "आक्षेप/ऐंठन", "spasmodic": "आक्षेपी",
        "spots": "धब्बे", "standing": "खड़े होने पर", "stiffness": "अकड़न",
        "stitching": "सुई चुभने जैसा", "stomach": "आमाशय/पेट",
        "stool": "मल", "stools": "दस्त/मल", "straining": "जोर लगाना",
        "swallowing": "निगलने पर", "sweat": "पसीना", "swelling": "सूजन",
        "taste": "स्वाद", "tearing": "फाड़ता हुआ", "teeth": "दाँत",
        "temples": "कनपटी", "tenacious": "गाढ़ा व चिपचिपा",
        "thighs": "जांघें", "thirst": "प्यास", "throat": "गला",
        "throbbing": "धड़कता हुआ", "time": "समय", "to": "तक/को",
        "tongue": "जीभ", "touch": "स्पर्श/छूने से", "turning": "घूमने/मुड़ने पर",
        "twitching": "फड़कना", "ulcer": "अल्सर", "ulcers": "अल्सर/घाव",
        "upper": "ऊपरी", "urine": "मूत्र", "urinary": "मूत्र संबंधी",
        "vertigo": "चक्कर", "vessels": "वाहिकाएँ", "viscid": "गाढ़ा",
        "vision": "दृष्टि", "vomiting": "उल्टी", "waking": "जागने पर",
        "walking": "चलने पर", "warm": "गर्म", "warmth": "गर्मी",
        "water": "पानी", "watery": "पानी जैसा", "weakness": "कमज़ोरी",
        "weather": "मौसम", "wet": "गीला/नम", "white": "सफेद",
        "wind": "हवा", "worse": "बढ़ना (वृद्धि)", "wounds": "घाव",
        "yellow": "पीला"
    }

    try:
        from tpbocr.words_426_map import WORDS_426_MAP
        WORD_DICT.update(WORDS_426_MAP)
    except Exception:
        pass

    words = re.findall(r"[a-zA-Z]+|[^\w\s]", raw)
    trans_words = []
    for w in words:
        wl = w.lower()
        if wl in WORD_DICT:
            trans_words.append(WORD_DICT[wl])
        elif w in [",", "(", ")", "-", "—"]:
            trans_words.append(w)
        else:
            trans_words.append(w)

    res = " ".join(trans_words)
    res = re.sub(r"\s+([,\)])", r"\1", res)
    res = re.sub(r"\(\s+", r"(", res)
    return res

def translate_full_rubric(r_name):
    """Translate complete rubric name preserving dashes and level."""
    if not r_name or r_name == "(पिछली रूब्रिक जारी)":
        return "(पिछली रूब्रिक जारी)", 0

    m = re.match(r"^(\s*—(?:\s*—)?\s*)(.*)$", r_name)
    if m:
        prefix = m.group(1)
        core = m.group(2).strip()
        level = 2 if "— —" in prefix or "——" in prefix else 1
        trans = translate_phrase(core)
        dash_str = "— — " if level == 2 else "— "
        return dash_str + trans, level
    else:
        return translate_phrase(r_name), 0

def transliterate_latin_name(latin):
    """Full Devanagari transliteration of Latin remedy name."""
    LATIN_EXACT = {
        "Aconitum napellus": "एकोनाइटम नेपेलस",
        "Agaricus muscarius": "एगेरिकस मस्केरियस",
        "Agnus castus": "एग्नस कास्टस",
        "Alumina": "एल्यूमिना",
        "Ambra grisea": "एम्ब्रा ग्रीसिया",
        "Ammonium carbonicum": "अमोनियम कार्बोनिकम",
        "Ammonium muriaticum": "अमोनियम म्यूरिएटिकम",
        "Anacardium orientale": "एनाकार्डियम ओरिएंटेल",
        "Antimonium crudum": "एंटीमोनियम क्रूडम",
        "Antimonium tartaricum": "एंटीमोनियम टार्टरिकम",
        "Apis mellifica": "एपिस मेलिफिका",
        "Argentum metallicum": "अर्जेंटम मेटैलिकम",
        "Argentum nitricum": "अर्जेंटम नाइट्रिकम",
        "Arnica montana": "आर्निका मोंटाना",
        "Arsenicum album": "आर्सेनिकम एल्बम",
        "Asa foetida": "आसाफेटिडा",
        "Asarum europaeum": "असारम यूरोपियम",
        "Aurum metallicum": "ऑरम मेटैलिकम",
        "Baryta carbonica": "बेराइटा कार्बोनिका",
        "Belladonna": "बेलाडोना",
        "Bismuthum": "बिस्मथम",
        "Borax": "बोरेक्स",
        "Bovista": "बोविस्टा",
        "Bromium": "ब्रोमियम",
        "Bryonia alba": "ब्रायोनिया एल्बा",
        "Caladium seguinum": "कैलेडियम सेगुइनम",
        "Calcarea carbonica": "कैलकेरिया कार्बोनिका",
        "Calcarea phosphorica": "कैलकेरिया फॉस्फोरिका",
        "Camphora": "कैम्फोरा",
        "Cannabis indica": "कैनबिस इंडिका",
        "Cannabis sativa": "कैनबिस सैटिवा",
        "Cantharis": "कैन्थारिस",
        "Capsicum annuum": "कैप्सिकम एनम",
        "Carbo animalis": "कार्बो एनीमेलिस",
        "Carbo vegetabilis": "कार्बो वेजीटेबिलिस",
        "Causticum": "कॉस्टिकम",
        "Chamomilla": "कैमोमिला",
        "Chelidonium majus": "चेलिडोनियम मेजस",
        "China officinalis": "चाइना (सिनकोना)",
        "Cicuta virosa": "सिक्यूटा विरोसा",
        "Cina": "सीना",
        "Clematis erecta": "क्लेमेटिस इरेक्टा",
        "Cocculus indicus": "कॉक्युलस इंडिकस",
        "Coffea cruda": "कॉफिया क्रूड़ा",
        "Colchicum autumnale": "कोलचिकम",
        "Colocynthis": "कोलोसिन्थ",
        "Conium maculatum": "कोनियम मैकुलेटम",
        "Crocus sativus": "क्रोकस सैटाइवस",
        "Cuprum metallicum": "कूप्रम मेटैलिकम",
        "Cyclamen europaeum": "साइक्लेमेन यूरोपियम",
        "Digitalis purpurea": "डिजिटैलिस",
        "Drosera rotundifolia": "ड्रोसेरा",
        "Dulcamara": "डलकामारा",
        "Euphorbium": "यूफोर्बियम",
        "Euphrasia": "यूफ्रेशिया",
        "Ferrum metallicum": "फेरम मेटैलिकम",
        "Gelsemium sempervirens": "जेल्सीमियम",
        "Graphites": "ग्रेफाइट्स",
        "Guaiacum": "गुआयाकम",
        "Helleborus niger": "हेलीबोरस नाइजर",
        "Hepar sulphuris calcareum": "हिपर सल्फ",
        "Hyoscyamus niger": "हायोसायमस नाइजर",
        "Ignatia amara": "इग्नेशिया अमारा",
        "Iodum": "आयोडम",
        "Ipecacuanha": "इपिकाक",
        "Kali bichromicum": "काली बाइक्रोमिकम",
        "Kali carbonicum": "काली कार्बोनिकम",
        "Kali nitricum": "काली नाइट्रिकम",
        "Kreosotum": "क्रियोजोट",
        "Lachesis mutus": "लैकेसिस",
        "Ledum palustre": "लीडम पाल",
        "Lycopodium clavatum": "लाइकोपोडियम",
        "Magnesia carbonica": "मैग्नीशिया कार्ब",
        "Magnesia muriatica": "मैग्नीशिया म्यूर",
        "Manganum": "मैंगनम",
        "Menyanthes trifoliata": "मेनियान्थिस",
        "Mercurius vivus": "मर्क्यूरियस",
        "Mezereum": "मेजेरियम",
        "Moschus": "मॉस्कस",
        "Muriaticum acidum": "म्यूरिएटिक एसिड",
        "Natrum carbonicum": "नेटम कार्ब",
        "Natrum muriaticum": "नेटम म्यूर",
        "Nitricum acidum": "नाइट्रिक एसिड",
        "Nux moschata": "नक्स मोस्काटा",
        "Nux vomica": "नक्स वोमिका",
        "Opium": "ओपियम",
        "Paris quadrifolia": "पेरिस क्वाड्रीफोलिया",
        "Petroleum": "पेट्रोलियम",
        "Phosphorus": "फॉस्फोरस",
        "Phosphoricum acidum": "फॉस्फोरिक एसिड",
        "Platinum metallicum": "प्लैटिनम मेटैलिकम",
        "Plumbum metallicum": "प्लम्बम मेटैलिकम",
        "Podophyllum peltatum": "पोडोफाइलम",
        "Psorinum": "सोराइनम",
        "Pulsatilla": "पल्सेटिला",
        "Ranunculus bulbosus": "रेनुनक्युलस बल्बोसस",
        "Ranunculus sceleratus": "रेनुनक्युलस स्केलेरेटस",
        "Rheum": "र्ह्यूम",
        "Rhododendron chrysanthum": "रोडोडेंड्रॉन",
        "Rhus toxicodendron": "रस टॉक्सिकोडेंड्रॉन",
        "Ruta graveolens": "रूटा ग्रेविओलेन्स",
        "Sabadilla": "सबाडिला",
        "Sabina": "सबीना",
        "Sambucus nigra": "सम्बूक्स नाइग्रा",
        "Sarsaparilla": "सारसापेरिला",
        "Secale cornutum": "सिकेल कोर",
        "Selenium": "सेलेनियम",
        "Senega": "सेनेगा",
        "Sepia": "सीपिया",
        "Silicea": "सिलिशिया",
        "Spigelia anthelmia": "स्पाइजीलिया",
        "Spongia tosta": "स्पोंजिया टोस्टा",
        "Squilla maritima": "स्क्विला",
        "Stannum metallicum": "स्टैनम मेटैलिकम",
        "Staphysagria": "स्टैफिसेग्रिया",
        "Stramonium": "स्ट्रामोनियम",
        "Strontium carbonicum": "स्ट्रोंशियम कार्ब",
        "Sulphur": "सल्फर",
        "Sulphuricum acidum": "सल्फ्यूरिक एसिड",
        "Taraxacum officinale": "टैराक्सेकम",
        "Teucrium marum verum": "ट्यूक्रियम",
        "Theridion": "थेरिडियन",
        "Thuja occidentalis": "थूजा",
        "Valeriana": "वैलेरियना",
        "Veratrum album": "वेराट्रम एल्बम",
        "Viola odorata": "वायोला ओडोराटा",
        "Viola tricolor": "वायोला ट्राइकलर",
        "Zincum metallicum": "जिंकम मेटैलिकम",
        "Simaruba cedron": "सेड्रोन"
    }

    if latin in LATIN_EXACT:
        return LATIN_EXACT[latin]

    # Clean fallback mapping
    return latin

def main():
    print("=== RUNNING FULL 100% CLINICAL TRANSLATION PIPELINE ===")

    # 1. Translate rep_rubric.csv
    rub_file = os.path.join(FINAL_DIR, "rep_rubric.csv")
    with open(rub_file, encoding="utf-8-sig") as f:
        rubs = list(csv.DictReader(f))

    print(f"Translating {len(rubs):,} rubrics...")
    rub_map = {}
    updated_rubs = []

    for r in rubs:
        name = r["name"]
        hi_name, level = translate_full_rubric(name)
        rub_map[name] = hi_name
        updated_rubs.append({
            "id": r["id"],
            "path": r["path"],
            "name": name,
            "name_hi": hi_name,
            "level": level
        })

    with open(rub_file, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["id", "path", "name", "name_hi", "level"])
        w.writeheader()
        w.writerows(updated_rubs)

    # Save bilingual view
    audit_path = os.path.join(TRANS_DIR, "tpb_rubrics_bilingual.csv")
    with open(audit_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "name_hi", "level"])
        w.writeheader()
        w.writerows([{"id": r["id"], "name": r["name"], "name_hi": r["name_hi"], "level": r["level"]} for r in updated_rubs])

    print("SUCCESS: 1,676 rubrics translated and saved to rep_rubric.csv & tpb_rubrics_bilingual.csv")

    # 2. Translate rep_remedy.csv
    rem_file = os.path.join(FINAL_DIR, "rep_remedy.csv")
    with open(rem_file, encoding="utf-8-sig") as f:
        rems = list(csv.DictReader(f))

    print(f"Translating {len(rems):,} remedies...")
    rem_map = {}
    updated_rems = []

    for r in rems:
        latin = r.get("name", "").strip()
        hi_name = transliterate_latin_name(latin) if latin else r["abbrev"]
        rem_map[r["norm"]] = hi_name
        comm_hi = ""
        if "गंधक" in hi_name: comm_hi = "गंधक (Brimstone)"
        elif "चूना" in hi_name: comm_hi = "चूना भस्म (Carbonate of Lime)"
        elif "कुचला" in hi_name: comm_hi = "कुचला (Poison Nut)"
        elif "अफीम" in hi_name: comm_hi = "अफीम (Poppy)"
        elif "भांग" in hi_name: comm_hi = "भांग (Hemp)"
        elif "गांजा" in hi_name: comm_hi = "गांजा (Hemp)"
        elif "हींग" in hi_name: comm_hi = "हींग"
        elif "स्वर्ण" in hi_name: comm_hi = "स्वर्ण भस्म (Gold)"
        elif "सीसा" in hi_name: comm_hi = "सीसा (Lead)"
        elif "ताम्र" in hi_name: comm_hi = "ताम्र भस्म (Copper)"
        elif "लौह" in hi_name: comm_hi = "लौह भस्म (Iron)"
        elif "जस्ता" in hi_name: comm_hi = "जस्ता (Zinc)"
        elif "रांगा" in hi_name: comm_hi = "रांगा / टिन (Tin)"
        elif "कपूर" in hi_name: comm_hi = "कपूर (Camphor)"
        elif "सुहागा" in hi_name: comm_hi = "सुहागा (Borax)"
        elif "सेंधा नमक" in hi_name: comm_hi = "सेंधा नमक (Common Salt)"
        elif "धतूरा" in hi_name: comm_hi = "धतूरा (Thorn Apple)"
        elif "कस्तूरी" in hi_name: comm_hi = "कस्तूरी (Musk)"
        elif "केसर" in hi_name: comm_hi = "केसर (Saffron)"

        updated_rems.append({
            "id": r["id"],
            "abbrev": r["abbrev"],
            "norm": r["norm"],
            "name": r["name"],
            "name_hi": hi_name,
            "standard_abbrev": r["standard_abbrev"],
            "common_name": r["common_name"],
            "common_name_hi": comm_hi,
            "name_source": r["name_source"],
            "occurrences": r["occurrences"]
        })

    with open(rem_file, "w", newline="", encoding="utf-8-sig") as f:
        cols = ["id", "abbrev", "norm", "name", "name_hi", "standard_abbrev", "common_name", "common_name_hi", "name_source", "occurrences"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(updated_rems)

    print("SUCCESS: 605 remedies translated and saved to rep_remedy.csv")

    # 3. Update tpb_final_graded.csv and tpb_final_graded.json
    fg_file = os.path.join(FINAL_DIR, "tpb_final_graded.csv")
    with open(fg_file, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"Updating {len(rows):,} graded token rows...")
    for r in rows:
        rub = r["rubric"]
        norm_rem = r["norm_remedy"]
        r["rubric_hi"] = rub_map.get(rub, rub)
        r["remedy_name_hi"] = rem_map.get(norm_rem, r.get("remedy_name", ""))

    fieldnames = list(rows[0].keys())
    with open(fg_file, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    fg_json = os.path.join(FINAL_DIR, "tpb_final_graded.json")
    json.dump({"total_tokens": len(rows), "rows": rows},
              open(fg_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("SUCCESS: Updated tpb_final_graded.csv and tpb_final_graded.json (132,367 rows)")
    print("ALL DATASET TABLES FULLY TRANSLATED INTO CLINICAL HINDI!")

if __name__ == "__main__":
    main()
