# -*- coding: utf-8 -*-
"""Comprehensive Remedy Name Authority and Normalization for TPB 1891.
Maps all historic TPB printed abbreviations to full Latin names, standard abbreviations,
and common names using core125 (Public Domain) and oorep authority databases.
"""
import os, sys, json, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPB_DATA = os.path.join(ROOT, "..", "tpb-data")
REFC = os.path.join(TPB_DATA, "reference")
if not os.path.isdir(REFC):
    REFC = os.path.join(TPB_DATA, "reference-copyright")

def nkey(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())

# Explicit authoritative mapping for TPB (Allen 1891 / Boenninghausen) abbreviations
# Key: normalized string -> (Full Latin Name, Standard Abbrev, Common Name, Source)
TPB_ALIASES = {
    'sul': ('Sulphur', 'Sulph.', 'Brimstone / Sublimed Sulphur', 'core125(PD)'),
    'rhus': ('Rhus toxicodendron', 'Rhus-t.', 'Poison Ivy', 'core125(PD)'),
    'calcc': ('Calcarea carbonica', 'Calc.', 'Carbonate of Lime', 'core125(PD)'),
    'kcarb': ('Kali carbonicum', 'Kali-c.', 'Carbonate of Potassium', 'core125(PD)'),
    'phoac': ('Phosphoricum acidum', 'Ph-ac.', 'Phosphoric Acid', 'core125(PD)'),
    'phosac': ('Phosphoricum acidum', 'Ph-ac.', 'Phosphoric Acid', 'core125(PD)'),
    'verata': ('Veratrum album', 'Verat.', 'White Hellebore', 'core125(PD)'),
    'varata': ('Veratrum album', 'Verat.', 'White Hellebore', 'core125(PD)'),
    'veruta': ('Veratrum album', 'Verat.', 'White Hellebore', 'core125(PD)'),
    'petrol': ('Petroleum', 'Petr.', 'Rock Oil / Crude Rock-Oil', 'core125(PD)'),
    'saba': ('Sabadilla', 'Sabad.', 'Cevadilla Seeds', 'core125(PD)'),
    'sba': ('Sabadilla', 'Sabad.', 'Cevadilla Seeds', 'core125(PD)'),
    'stan': ('Stannum metallicum', 'Stann.', 'Tin', 'core125(PD)'),
    'stam': ('Stannum metallicum', 'Stann.', 'Tin', 'core125(PD)'),
    'spo': ('Spongia tosta', 'Spong.', 'Roasted Sponge', 'core125(PD)'),
    'fer': ('Ferrum metallicum', 'Ferr.', 'Iron', 'core125(PD)'),
    'pb': ('Plumbum metallicum', 'Plb.', 'Lead', 'core125(PD)'),
    'antcr': ('Antimonium crudum', 'Ant-c.', 'Black Sulphide of Antimony', 'core125(PD)'),
    'anscr': ('Antimonium crudum', 'Ant-c.', 'Black Sulphide of Antimony', 'core125(PD)'),
    'sabi': ('Sabina', 'Sabin.', 'Savin', 'core125(PD)'),
    'cup': ('Cuprum metallicum', 'Cupr.', 'Copper', 'core125(PD)'),
    'kre': ('Kreosotum', 'Kreos.', 'Creosote (Beechwood)', 'core125(PD)'),
    'crep': ('Kreosotum', 'Kreos.', 'Creosote (Beechwood)', 'core125(PD)'),
    'rhodo': ('Rhododendron chrysanthum', 'Rhod.', 'Yellow Snow-Rose', 'core125(PD)'),
    'rhoda': ('Rhododendron chrysanthum', 'Rhod.', 'Yellow Snow-Rose', 'core125(PD)'),
    'amcarb': ('Ammonium carbonicum', 'Am-c.', 'Carbonate of Ammonia', 'core125(PD)'),
    'amcurb': ('Ammonium carbonicum', 'Am-c.', 'Carbonate of Ammonia', 'core125(PD)'),
    'amnc': ('Ammonium carbonicum', 'Am-c.', 'Carbonate of Ammonia', 'core125(PD)'),
    'secc': ('Secale cornutum', 'Sec.', 'Ergot of Rye', 'core125(PD)'),
    'gel': ('Gelsemium sempervirens', 'Gels.', 'Yellow Jasmine', 'allen1891(canonical)'),
    'oleand': ('Oleander', 'Oleand.', 'Rose Laurel', 'core125(PD)'),
    'cannabs': ('Cannabis sativa', 'Cann-s.', 'Hemp', 'core125(PD)'),
    'canabs': ('Cannabis sativa', 'Cann-s.', 'Hemp', 'core125(PD)'),
    'cannab': ('Cannabis sativa', 'Cann-s.', 'Hemp', 'core125(PD)'),
    'squ': ('Squilla maritima', 'Squil.', 'Sea Onion', 'core125(PD)'),
    'kbi': ('Kali bichromicum', 'Kali-bi.', 'Bichromate of Potash', 'allen1891(canonical)'),
    'kb': ('Kali bichromicum', 'Kali-bi.', 'Bichromate of Potash', 'allen1891(canonical)'),
    'kbl': ('Kali bichromicum', 'Kali-bi.', 'Bichromate of Potash', 'allen1891(canonical)'),
    'cannabi': ('Cannabis indica', 'Cann-i.', 'Indian Hemp / Hashish', 'allen1891(canonical)'),
    'stro': ('Strontium carbonicum', 'Stront-c.', 'Carbonate of Strontia', 'core125(PD)'),
    'sto': ('Strontium carbonicum', 'Stront-c.', 'Carbonate of Strontia', 'core125(PD)'),
    'bap': ('Baptisia tinctoria', 'Bapt.', 'Wild Indigo', 'allen1891(canonical)'),
    'bep': ('Baptisia tinctoria', 'Bapt.', 'Wild Indigo', 'allen1891(canonical)'),
    'bay': ('Baptisia tinctoria', 'Bapt.', 'Wild Indigo', 'allen1891(canonical)'),
    'mos': ('Moschus', 'Mosch.', 'Musk', 'core125(PD)'),
    'knit': ('Kali nitricum', 'Kali-n.', 'Nitre / Saltpetre', 'core125(PD)'),
    'kitnit': ('Kali nitricum', 'Kali-n.', 'Nitre / Saltpetre', 'core125(PD)'),
    'sele': ('Selenium', 'Selen.', 'Selenium', 'core125(PD)'),
    'euphorb': ('Euphorbium', 'Euph.', 'Spurge Flax', 'core125(PD)'),
    'euphor': ('Euphorbium', 'Euph.', 'Spurge Flax', 'core125(PD)'),
    'euphurb': ('Euphorbium', 'Euph.', 'Spurge Flax', 'core125(PD)'),
    'tar': ('Taraxacum officinale', 'Tarax.', 'Dandelion', 'core125(PD)'),
    'tare': ('Taraxacum officinale', 'Tarax.', 'Dandelion', 'core125(PD)'),
    'cyc': ('Cyclamen europaeum', 'Cycl.', 'Sow-Bread', 'core125(PD)'),
    'pod': ('Podophyllum peltatum', 'Podo.', 'May-Apple / Mandrake', 'allen1891(canonical)'),
    'mar': ('Teucrium marum verum', 'Teucr.', 'Cat-Thyme', 'core125(PD)'),
    'crotal': ('Crotalus horridus', 'Crot-h.', 'Rattlesnake Venom', 'allen1891(canonical)'),
    'crotul': ('Crotalus horridus', 'Crot-h.', 'Rattlesnake Venom', 'allen1891(canonical)'),
    'viot': ('Viola tricolor', 'Vio-t.', 'Pansy / Heartsease', 'core125(PD)'),
    'vict': ('Viola tricolor', 'Vio-t.', 'Pansy / Heartsease', 'core125(PD)'),
    'pso': ('Psorinum', 'Psor.', 'Psorinum / Scabies Vesicle', 'allen1891(canonical)'),
    'irisv': ('Iris versicolor', 'Iris', 'Blue Flag', 'allen1891(canonical)'),
    'lith': ('Lithium carbonicum', 'Lith-c.', 'Carbonate of Lithium', 'allen1891(canonical)'),
    'lit': ('Lithium carbonicum', 'Lith-c.', 'Carbonate of Lithium', 'allen1891(canonical)'),
    'carbsul': ('Carboneum sulphuratum', 'Carbn-s.', 'Bisulphide of Carbon', 'allen1891(canonical)'),
    'carbs': ('Carboneum sulphuratum', 'Carbn-s.', 'Bisulphide of Carbon', 'allen1891(canonical)'),
    'vioo': ('Viola odorata', 'Vio-o.', 'Sweet-Scented Violet', 'core125(PD)'),
    'violao': ('Viola odorata', 'Vio-o.', 'Sweet-Scented Violet', 'core125(PD)'),
    'calcph': ('Calcarea phosphorica', 'Calc-p.', 'Phosphate of Lime', 'allen1891(canonical)'),
    'apocc': ('Apocynum cannabinum', 'Apoc.', 'Indian Hemp (American)', 'allen1891(canonical)'),
    'apoce': ('Apocynum cannabinum', 'Apoc.', 'Indian Hemp (American)', 'allen1891(canonical)'),
    'crottig': ('Croton tiglium', 'Croto-t.', 'Croton Oil Seeds', 'core125(PD)'),
    'hydac': ('Hydrocyanicum acidum', 'Hydr-ac.', 'Prussic Acid', 'allen1891(canonical)'),
    'hydras': ('Hydrastis canadensis', 'Hydr.', 'Golden Seal', 'allen1891(canonical)'),
    'ced': ('Cedron', 'Cedr.', 'Rattlesnake Bean', 'allen1891(canonical)'),
    'kbr': ('Kali bromatum', 'Kali-br.', 'Bromide of Potash', 'allen1891(canonical)'),
    'kiod': ('Kali iodatum', 'Kali-i.', 'Iodide of Potash', 'allen1891(canonical)'),
    'rumex': ('Rumex crispus', 'Rumx.', 'Yellow Dock', 'allen1891(canonical)'),
    'cinnab': ('Cinnabaris', 'Cinnb.', 'Red Sulphide of Mercury', 'allen1891(canonical)'),
    'naj': ('Naja tripudians', 'Naja', 'Cobra Venom', 'allen1891(canonical)'),
    'nagm': ('Naja tripudians', 'Naja', 'Cobra Venom', 'allen1891(canonical)'),
    'pru': ('Prunus spinosa', 'Prun.', 'Blackthorn', 'core125(PD)'),
    'gam': ('Gambogia', 'Gamb.', 'Gummi Gutti', 'core125(PD)'),
    'kchl': ('Kali chloricum', 'Kali-chl.', 'Chlorate of Potassium', 'allen1891(canonical)'),
    'millef': ('Millefolium', 'Mill.', 'Yarrow', 'core125(PD)'),
    'arsiod': ('Arsenicum iodatum', 'Ars-i.', 'Iodide of Arsenic', 'allen1891(canonical)'),
    'lobi': ('Lobelia inflata', 'Lob.', 'Indian Tobacco', 'allen1891(canonical)'),
    'ferph': ('Ferrum phosphoricum', 'Ferr-p.', 'Phosphate of Iron', 'allen1891(canonical)'),
    'ferphos': ('Ferrum phosphoricum', 'Ferr-p.', 'Phosphate of Iron', 'allen1891(canonical)'),
    'vibop': ('Viburnum opulus', 'Vib.', 'High Cranberry / Cramp Bark', 'allen1891(canonical)'),
    'vipop': ('Viburnum opulus', 'Vib.', 'High Cranberry / Cramp Bark', 'allen1891(canonical)'),
    'amyl': ('Amylenum nitrosum', 'Aml-ns.', 'Amyl Nitrite', 'allen1891(canonical)'),
    'sangn': ('Sanguinaria nitrica', 'Sang-n.', 'Nitrate of Sanguinarine', 'allen1891(canonical)'),
    'coral': ('Corallium rubrum', 'Cor-r.', 'Red Coral', 'allen1891(canonical)'),
    'cor': ('Corallium rubrum', 'Cor-r.', 'Red Coral', 'allen1891(canonical)'),
    'acac': ('Aceticum acidum', 'Acet-ac.', 'Glacial Acetic Acid', 'allen1891(canonical)'),
    'acet': ('Aceticum acidum', 'Acet-ac.', 'Glacial Acetic Acid', 'allen1891(canonical)'),
    'cornc': ('Cornus circinata', 'Corn.', 'Round-Leaved Dogwood', 'allen1891(canonical)'),
    'grind': ('Grindelia robusta', 'Grin.', 'Rosin-Wood', 'allen1891(canonical)'),
    'plant': ('Plantago major', 'Plan.', 'Plantain', 'allen1891(canonical)'),
    'sin': ('Sinapis nigra', 'Sin-n.', 'Black Mustard', 'allen1891(canonical)'),
    'atrop': ('Atropinum', 'Atro.', 'Atropine (Alkaloid of Belladonna)', 'allen1891(canonical)'),
    'po': ('Paeonia officinalis', 'Paeon.', 'Peony', 'allen1891(canonical)'),
    'paeo': ('Paeonia officinalis', 'Paeon.', 'Peony', 'allen1891(canonical)'),
    'murex': ('Murex purpurea', 'Murx.', 'Purple Fish', 'allen1891(canonical)'),
    'calcac': ('Calcarea acetica', 'Calc-act.', 'Acetate of Lime', 'allen1891(canonical)'),
    'natars': ('Natrum arsenicosum', 'Nat-ar.', 'Arseniate of Soda', 'allen1891(canonical)'),
    'nata': ('Natrum arsenicosum', 'Nat-ar.', 'Arseniate of Soda', 'allen1891(canonical)'),
    'chloral': ('Chloralum hydratum', 'Chlol.', 'Chloral Hydrate', 'allen1891(canonical)'),
    'abs': ('Absinthium', 'Absin.', 'Wormwood', 'allen1891(canonical)'),
    'trill': ('Trillium pendulum', 'Tril.', 'White Beth-Root', 'allen1891(canonical)'),
    'abc': ('Abies canadensis', 'Abies-c.', 'Hemlock Spruce', 'allen1891(canonical)'),
    'jat': ('Jatropha curcas', 'Jatr.', 'Purging Nut', 'core125(PD)'),
    'ura': ('Uranium nitricum', 'Uran-n.', 'Nitrate of Uranium', 'allen1891(canonical)'),
    'buf': ('Bufo rana', 'Bufo', 'Toad Poison', 'allen1891(canonical)'),
    'cads': ('Cadmium sulphuratum', 'Cadm-s.', 'Sulphide of Cadmium', 'allen1891(canonical)'),
    'abn': ('Abies nigra', 'Abies-n.', 'Black Spruce', 'allen1891(canonical)'),
    'equi': ('Equisetum hyemale', 'Equis.', 'Scouring Rush', 'allen1891(canonical)'),
    'amb': ('Ammonium benzoicum', 'Am-bz.', 'Benzoate of Ammonia', 'allen1891(canonical)'),
    'barac': ('Baryta acetica', 'Bar-act.', 'Acetate of Barium', 'core125(PD)'),
    'card': ('Carduus marianus', 'Card-m.', 'St. Marys Thistle', 'allen1891(canonical)'),
    'sum': ('Sumbul', 'Sumb.', 'Musk-Root', 'allen1891(canonical)'),
    'parei': ('Pareira brava', 'Pareir.', 'Virgin Vine', 'allen1891(canonical)'),
    'pare': ('Pareira brava', 'Pareir.', 'Virgin Vine', 'allen1891(canonical)'),
    'calend': ('Calendula officinalis', 'Calen.', 'Marigold', 'allen1891(canonical)'),
    'act': ('Actaea racemosa (Cimicifuga)', 'Cimic.', 'Black Cohosh', 'allen1891(canonical)'),
    'acetum': ('Acetum vegetabile', 'Acet-ac.', 'Vinegar', 'core125(PD)'),
    'acetumveget': ('Acetum vegetabile', 'Acet-ac.', 'Vinegar', 'core125(PD)'),
    'acetveg': ('Acetum vegetabile', 'Acet-ac.', 'Vinegar', 'core125(PD)'),
    'naph': ('Naphthalinum', 'Naph.', 'Naphthaline (Tar Product)', 'allen1891(canonical)'),
    'bar': ('Baryta carbonica', 'Bar-c.', 'Carbonate of Barium', 'core125(PD)'),
    'myr': ('Myrica cerifera', 'Myric.', 'Bayberry / Wax Myrtle', 'allen1891(canonical)'),
    'antsaur': ('Antimonium sulfuratum auratum', 'Ant-s-aur.', 'Golden Sulphuret of Antimony', 'allen1891(canonical)'),
    'spirnitdul': ('Spiritus nitri dulcis', 'Spir-n-d.', 'Sweet Spirit of Nitre', 'core125(PD)'),
    'spirnitdulc': ('Spiritus nitri dulcis', 'Spir-n-d.', 'Sweet Spirit of Nitre', 'core125(PD)'),
    'spirnitd': ('Spiritus nitri dulcis', 'Spir-n-d.', 'Sweet Spirit of Nitre', 'core125(PD)'),
    'chromac': ('Chromicum acidum', 'Chro-ac.', 'Chromic Acid', 'allen1891(canonical)'),
    'feriod': ('Ferrum iodatum', 'Ferr-i.', 'Iodide of Iron', 'allen1891(canonical)'),
    'popt': ('Populus tremuloides', 'Pop-t.', 'American Aspen', 'allen1891(canonical)'),
    'strop': ('Strophanthus hispidus', 'Stroph.', 'Kombe Seed', 'allen1891(canonical)'),
    'eryng': ('Eryngium aquaticum', 'Ery-a.', 'Button Snake-Root', 'allen1891(canonical)'),
    'alumen': ('Alumen', 'Alumn.', 'Potassa-Alum', 'allen1891(canonical)'),
    'tan': ('Tanacetum vulgare', 'Tanac.', 'Tansy', 'allen1891(canonical)'),
    'chlorum': ('Chlorum', 'Chlo.', 'Chlorine Gas in Water', 'allen1891(canonical)'),
    'chln': ('Chlorum', 'Chlo.', 'Chlorine Gas in Water', 'allen1891(canonical)'),
    'thlasp': ('Thlaspi bursa pastoris', 'Thlaspi', 'Shepherds Purse', 'allen1891(canonical)'),
    'urt': ('Urtica urens', 'Urt-u.', 'Stinging Nettle', 'allen1891(canonical)'),
    'litt': ('Lilium tigrinum', 'Lil-t.', 'Tiger Lily', 'allen1891(canonical)'),
    'liltig': ('Lilium tigrinum', 'Lil-t.', 'Tiger Lily', 'allen1891(canonical)'),
    'lil': ('Lilium tigrinum', 'Lil-t.', 'Tiger Lily', 'allen1891(canonical)'),
    'calcfl': ('Calcarea fluorica', 'Calc-f.', 'Fluoride of Lime', 'allen1891(canonical)'),
    'cocaine': ('Cocainum', 'Cocaine', 'Cocaine Hydrochloride', 'allen1891(canonical)'),
    'km': ('Kali muriaticum', 'Kali-m.', 'Chloride of Potassium', 'allen1891(canonical)'),
    'gnap': ('Gnaphalium polycephalum', 'Gnaph.', 'Cud-Weed', 'allen1891(canonical)'),
    'ant': ('Antimonium crudum', 'Ant-c.', 'Antimony', 'core125(PD)'),
    'calciod': ('Calcarea iodata', 'Calc-i.', 'Iodide of Lime', 'allen1891(canonical)'),
    'apomor': ('Apomorphinum muriaticum', 'Apom.', 'Apomorphia Hydrochloride', 'allen1891(canonical)'),
    'cereum': ('Cerium oxalicum', 'Cer-ox.', 'Oxalate of Cerium', 'allen1891(canonical)'),
    'cerium': ('Cerium oxalicum', 'Cer-ox.', 'Oxalate of Cerium', 'allen1891(canonical)'),
    'alst': ('Alstonia scholaris', 'Alst.', 'Dita Bark / Bitter Bark', 'allen1891(canonical)'),
    'poly': ('Polyporus officinalis', 'Polyp.', 'Larch Agaric', 'allen1891(canonical)'),
    'polyp': ('Polyporus officinalis', 'Polyp.', 'Larch Agaric', 'allen1891(canonical)'),
    'col': ('Colchicum autumnale', 'Colch.', 'Meadow Saffron', 'core125(PD)'),
    'oenan': ('Oenanthe crocata', 'Oena.', 'Water Hemlock', 'allen1891(canonical)'),
    'antars': ('Antimonium arsenicosum', 'Ant-ar.', 'Arsenite of Antimony', 'allen1891(canonical)'),
    'sc': ('Aesculus hippocastanum', 'Aesc.', 'Horse Chestnut', 'allen1891(canonical)'),
    'th': ('Aethusa cynapium', 'Aeth.', 'Fools Parsley', 'allen1891(canonical)'),
    'piper': ('Piper nigrum', 'Pip-n.', 'Black Pepper', 'allen1891(canonical)'),
    'eurper': ('Eupatorium perfoliatum', 'Eup-per.', 'Boneset / Thoroughwort', 'allen1891(canonical)'),
    'electric': ('Electricitas', 'Electr.', 'Electricity', 'allen1891(canonical)'),
    'pho': ('Phosphorus', 'Phos.', 'Phosphorus', 'core125(PD)'),
    'thos': ('Phosphorus', 'Phos.', 'Phosphorus', 'core125(PD)'),
    'mag': ('Magnesia carbonica', 'Mag-c.', 'Carbonate of Magnesia', 'core125(PD)'),
    'magnm': ('Magnesia muriatica', 'Mag-m.', 'Muriate of Magnesia', 'core125(PD)'),
    'maym': ('Magnesia muriatica', 'Mag-m.', 'Muriate of Magnesia', 'core125(PD)'),
    'merccor': ('Mercurius corrosivus', 'Merc-c.', 'Corrosive Sublimate', 'allen1891(canonical)'),
    'ammur': ('Ammonium muriaticum', 'Am-m.', 'Sal Ammoniac', 'core125(PD)'),
    'natac': ('Natrum aceticum', 'Nat-act.', 'Acetate of Soda', 'allen1891(canonical)'),
    'argnn': ('Argentum nitricum', 'Arg-n.', 'Nitrate of Silver', 'allen1891(canonical)'),
    'agnn': ('Argentum nitricum', 'Arg-n.', 'Nitrate of Silver', 'allen1891(canonical)'),
    'cucur': ('Cucurbita pepo', 'Cuc-p.', 'Pumpkin Seed', 'allen1891(canonical)'),
    'cuar': ('Curare', 'Cur.', 'Arrow Poison', 'allen1891(canonical)'),
    'cura': ('Curare', 'Cur.', 'Arrow Poison', 'allen1891(canonical)'),
    'gram': ('Granatum', 'Gran.', 'Pomegranate Bark', 'core125(PD)'),
    'jalap': ('Jalapa', 'Jal.', 'Jalap Root', 'allen1891(canonical)'),
    'diosc': ('Dioscorea villosa', 'Dios.', 'Wild Yam', 'allen1891(canonical)'),
    'throm': ('Trombidium muscae', 'Tromb.', 'Harvest Mite', 'allen1891(canonical)'),
    'hum': ('Humulus lupulus', 'Lup.', 'Hops', 'allen1891(canonical)'),
    'coccin': ('Coccinella septempunctata', 'Coccin.', 'Lady-Bird', 'allen1891(canonical)'),
    'lap': ('Lapis albus', 'Lap-a.', 'Gneiss Stone', 'allen1891(canonical)'),
    'vibpr': ('Viburnum prunifolium', 'Vib-p.', 'Black Haw', 'allen1891(canonical)'),
    'coc': ('Cocculus indicus', 'Cocc.', 'Indian Cockle', 'core125(PD)'),
    'coce': ('Cocculus indicus', 'Cocc.', 'Indian Cockle', 'core125(PD)'),
    'magnol': ('Magnolia grandiflora', 'Magn-gl.', 'Magnolia', 'allen1891(canonical)'),
    'maynol': ('Magnolia grandiflora', 'Magn-gl.', 'Magnolia', 'allen1891(canonical)'),
    'mex': ('Mezereum', 'Mez.', 'Spurge Olive', 'core125(PD)'),
    'amphos': ('Ammonium phosphoricum', 'Am-p.', 'Phosphate of Ammonia', 'allen1891(canonical)'),
    'calot': ('Calotropis gigantea', 'Calo.', 'Madar Bark', 'allen1891(canonical)'),
    'hydroc': ('Hydrocotyle asiatica', 'Hydrc.', 'Indian Pennywort', 'allen1891(canonical)'),
    'pr': ('Paris quadrifolia', 'Par.', 'One-Berry', 'core125(PD)'),
    'nuzv': ('Nux vomica', 'Nux-v.', 'Poison Nut', 'core125(PD)'),
    'dirca': ('Dirca palustris', 'Dirc.', 'Leatherwood', 'allen1891(canonical)'),
    'dols': ('Dolichos pruriens', 'Dol.', 'Cowhage', 'allen1891(canonical)'),
    'rhsn': ('Rhus toxicodendron', 'Rhus-t.', 'Poison Ivy', 'core125(PD)'),
    'rhvs': ('Rhus toxicodendron', 'Rhus-t.', 'Poison Ivy', 'core125(PD)'),
    'cunth': ('Cantharis', 'Canth.', 'Spanish Fly', 'core125(PD)'),
    'strum': ('Stramonium', 'Stram.', 'Thorn-Apple', 'core125(PD)'),
    'stran': ('Stramonium', 'Stram.', 'Thorn-Apple', 'core125(PD)'),
    'sup': ('Sulphur', 'Sulph.', 'Brimstone', 'core125(PD)'),
    'sui': ('Sulphur', 'Sulph.', 'Brimstone', 'core125(PD)'),
    'niaac': ('Nitricum acidum', 'Nit-ac.', 'Nitric Acid', 'core125(PD)'),
    'sal': ('Salix nigra', 'Sal-n.', 'Black Willow', 'allen1891(canonical)'),
    'stap': ('Staphysagria', 'Staph.', 'Stavesacre', 'core125(PD)'),
    'stapn': ('Staphysagria', 'Staph.', 'Stavesacre', 'core125(PD)'),
    'vebatv': ('Veratrum viride', 'Verat-v.', 'Green Hellebore', 'allen1891(canonical)'),
    'saccharum': ('Saccharum officinale', 'Sacch.', 'Cane Sugar', 'allen1891(canonical)'),
    'serpentaria': ('Aristolochia serpentaria', 'Arist-s.', 'Virginia Snake-Root', 'allen1891(canonical)'),
    'succuscitri': ('Citrus limonum (Succus citri)', 'Cit-l.', 'Lemon Juice', 'core125(PD)'),
    'citrisuccus': ('Citrus limonum (Succus citri)', 'Cit-l.', 'Lemon Juice', 'core125(PD)'),
    'fes': ('Ferrum metallicum', 'Ferr.', 'Iron', 'core125(PD)'),
    'cmic': ('Cimicifuga racemosa', 'Cimic.', 'Black Cohosh', 'allen1891(canonical)'),
    'ctmic': ('Cimicifuga racemosa', 'Cimic.', 'Black Cohosh', 'allen1891(canonical)'),
    'nacc': ('Natrum carbonicum', 'Nat-c.', 'Carbonate of Soda', 'core125(PD)'),
    'nac': ('Natrum carbonicum', 'Nat-c.', 'Carbonate of Soda', 'core125(PD)'),
    'nat': ('Natrum carbonicum', 'Nat-c.', 'Carbonate of Soda', 'core125(PD)'),
    'nate': ('Natrum carbonicum', 'Nat-c.', 'Carbonate of Soda', 'core125(PD)'),
    'acids': ('Acidum (Mineral & Vegetable Acids)', 'Acids', 'Acids Group', 'core125(PD)'),
    'bellc': ('Belladonna', 'Bell.', 'Deadly Nightshade', 'core125(PD)'),
    'semcarvi': ('Carum carvi (Semina carvi)', 'Carvi', 'Caraway Seeds', 'core125(PD)'),
    'alcohol': ('Alcohol', 'Alcohol', 'Alcohol', 'core125(PD)'),
    'plot': ('Platanus occidentalis', 'Platan.', 'Buttonwood / Sycamore', 'allen1891(canonical)'),
    'jod': ('Iodum', 'Iod.', 'Iodine', 'core125(PD)'),
    'coust': ('Causticum', 'Caust.', 'Hahnemanns Tinctura Acris', 'core125(PD)'),
    'spirvini': ('Spiritus vini', 'Spir-v.', 'Alcohol / Spirit of Wine', 'core125(PD)'),
    'kali': ('Kali (Potassium Group)', 'Kali', 'Potash Group', 'allen1891(canonical)'),
    'dul': ('Dulcamara', 'Dulc.', 'Bittersweet', 'core125(PD)'),
    'meng': ('Menyanthes trifoliata', 'Meny.', 'Buckbean', 'core125(PD)'),
    'plumb': ('Plumbum metallicum', 'Plb.', 'Lead', 'core125(PD)'),
    'oenot': ('Oenothera biennis', 'Oeno.', 'Evening Primrose', 'allen1891(canonical)'),
    'china': ('Cinchona officinalis (China)', 'Chin.', 'Peruvian Bark', 'core125(PD)'),
    'coccc': ('Coccus cacti', 'Cocc-c.', 'Cochineal', 'allen1891(canonical)'),
    'lithlact': ('Lithium lacticum', 'Lith-l.', 'Lactate of Lithium', 'allen1891(canonical)'),
    'astr': ('Asterias rubens', 'Ast-r.', 'Starfish', 'allen1891(canonical)'),
    'culad': ('Caladium seguinum', 'Calad.', 'American Arum', 'core125(PD)'),
    'jug': ('Juglans cinerea', 'Jug-c.', 'Butternut', 'allen1891(canonical)'),
    'verta': ('Veratrum album', 'Verat.', 'White Hellebore', 'core125(PD)'),
    'cerevisia': ('Cerevisia fermentum', 'Cerev.', 'Bakers Yeast', 'allen1891(canonical)'),
    'lac': ('Lac defloratum', 'Lac-d.', 'Skimmed Cow Milk', 'allen1891(canonical)'),
    'chem': ('Chamomilla', 'Cham.', 'German Chamomile', 'core125(PD)'),
    'salviaoff': ('Salvia officinalis', 'Sal-o.', 'Garden Sage', 'core125(PD)'),
    'hap': ('Hepar sulphuris calcareum', 'Hep.', 'Hahnemanns Calcium Sulphide', 'core125(PD)'),
    'maug': ('Manganum aceticum / metallicum', 'Mang.', 'Manganese', 'core125(PD)'),
    'ambra': ('Ambra grisea', 'Ambr.', 'Ambergris', 'core125(PD)'),
    'canst': ('Causticum', 'Caust.', 'Hahnemanns Tinctura Acris', 'core125(PD)'),
    'acetumveg': ('Acetum vegetabile', 'Acet-ac.', 'Vinegar', 'core125(PD)'),
    'cannabt': ('Cannabis sativa', 'Cann-s.', 'Hemp', 'core125(PD)'),
    'nabs': ('Cannabis sativa', 'Cann-s.', 'Hemp', 'core125(PD)'),
    'nabi': ('Cannabis indica', 'Cann-i.', 'Indian Hemp', 'allen1891(canonical)')
}

# Compound tokens (two remedies printed together without a comma in OCR)
COMPOUND_TOKENS = {
    'natcnatm': ('Natrum carbonicum & Natrum muriaticum', 'Nat-c. + Nat-m.', 'Nat-c & Nat-m', 'compound-ocr'),
    'phoacplat': ('Phosphoricum acidum & Platinum', 'Ph-ac. + Plat.', 'Ph-ac & Plat', 'compound-ocr'),
    'sulsulac': ('Sulphur & Sulphuricum acidum', 'Sulph. + Sul-ac.', 'Sulph & Sul-ac', 'compound-ocr'),
    'aescallc': ('Aesculus hippocastanum & Allium cepa', 'Aesc. + All-c.', 'Aesc & All-c', 'compound-ocr'),
    'natmnuxm': ('Natrum muriaticum & Nux moschata', 'Nat-m. + Nux-m.', 'Nat-m & Nux-m', 'compound-ocr'),
    'sarssecc': ('Sarsaparilla & Secale cornutum', 'Sars. + Sec.', 'Sars & Sec', 'compound-ocr'),
    'natcnuxm': ('Natrum carbonicum & Nux moschata', 'Nat-c. + Nux-m.', 'Nat-c & Nux-m', 'compound-ocr'),
    'antcrantt': ('Antimonium crudum & Antimonium tartaricum', 'Ant-c. + Ant-t.', 'Ant-c & Ant-t', 'compound-ocr'),
    'seccseneg': ('Secale cornutum & Senega', 'Sec. + Seneg.', 'Sec & Seneg', 'compound-ocr'),
    'nuxvpetrol': ('Nux vomica & Petroleum', 'Nux-v. + Petr.', 'Nux-v & Petr', 'compound-ocr'),
    'parphoac': ('Paris quadrifolia & Phosphoricum acidum', 'Par. + Ph-ac.', 'Par & Ph-ac', 'compound-ocr'),
    'ranbrans': ('Ranunculus bulbosus & Ranunculus sceleratus', 'Ran-b. + Ran-s.', 'Ran-b & Ran-s', 'compound-ocr'),
    'picacpso': ('Picricum acidum & Psorinum', 'Pic-ac. + Psor.', 'Pic-ac & Psor', 'compound-ocr'),
    'barccaust': ('Baryta carbonica & Causticum', 'Bar-c. + Caust.', 'Bar-c & Caust', 'compound-ocr'),
    'anacantcr': ('Anacardium orientale & Antimonium crudum', 'Anac. + Ant-c.', 'Anac & Ant-c', 'compound-ocr'),
    'fereupper': ('Ferrum metallicum & Eupatorium perfoliatum', 'Ferr. + Eup-per.', 'Ferr & Eup-per', 'compound-ocr'),
    'sulacther': ('Sulphuricum acidum & Theridion', 'Sul-ac. + Ther.', 'Sul-ac & Ther', 'compound-ocr'),
    'kcarbknit': ('Kali carbonicum & Kali nitricum', 'Kali-c. + Kali-n.', 'Kali-c & Kali-n', 'compound-ocr'),
    'sulsulacthuj': ('Sulphur, Sulphuricum acidum & Thuja', 'Sulph. + Sul-ac. + Thuj.', 'Sulph, Sul-ac & Thuj', 'compound-ocr'),
    'amcarbamm': ('Ammonium carbonicum & Ammonium muriaticum', 'Am-c. + Am-m.', 'Am-c & Am-m', 'compound-ocr'),
    'nitacnuxv': ('Nitricum acidum & Nux vomica', 'Nit-ac. + Nux-v.', 'Nit-ac & Nux-v', 'compound-ocr'),
    'knitlach': ('Kali nitricum & Lachesis', 'Kali-n. + Lach.', 'Kali-n & Lach', 'compound-ocr'),
    'kcarbnatc': ('Kali carbonicum & Natrum carbonicum', 'Kali-c. + Nat-c.', 'Kali-c & Nat-c', 'compound-ocr'),
    'krelilt': ('Kreosotum & Lilium tigrinum', 'Kreos. + Lil-t.', 'Kreos & Lil-t', 'compound-ocr'),
    'brycalcc': ('Bryonia alba & Calcarea carbonica', 'Bry. + Calc.', 'Bry & Calc', 'compound-ocr'),
    'nuxvrhus': ('Nux vomica & Rhus toxicodendron', 'Nux-v. + Rhus-t.', 'Nux-v & Rhus-t', 'compound-ocr'),
    'carbvcham': ('Carbo vegetabilis & Chamomilla', 'Carb-v. + Cham.', 'Carb-v & Cham', 'compound-ocr'),
    'calcccamph': ('Calcarea carbonica & Camphora', 'Calc. + Camph.', 'Calc & Camph', 'compound-ocr'),
    'antcrars': ('Antimonium crudum & Arsenicum album', 'Ant-c. + Ars.', 'Ant-c & Ars', 'compound-ocr'),
    'aurbarc': ('Aurum metallicum & Baryta carbonica', 'Aur. + Bar-c.', 'Aur & Bar-c', 'compound-ocr'),
    'muracplat': ('Muriaticum acidum & Platinum', 'Mur-ac. + Plat.', 'Mur-ac & Plat', 'compound-ocr'),
    'knitkre': ('Kali nitricum & Kreosotum', 'Kali-n. + Kreos.', 'Kali-n & Kreos', 'compound-ocr'),
    'hydachyos': ('Hydrocyanicum acidum & Hyoscyamus', 'Hydr-ac. + Hyos.', 'Hydr-ac & Hyos', 'compound-ocr'),
    'ransrheum': ('Ranunculus sceleratus & Rheum', 'Ran-s. + Rheum', 'Ran-s & Rheum', 'compound-ocr'),
    'agnamcarb': ('Agnus castus & Ammonium carbonicum', 'Agn. + Am-c.', 'Agn & Am-c', 'compound-ocr'),
    'sepilsil': ('Sepia & Silicea', 'Sep. + Sil.', 'Sep & Sil', 'compound-ocr'),
    'arnars': ('Arnica montana & Arsenicum album', 'Arn. + Ars.', 'Arn & Ars', 'compound-ocr'),
    'bovbrom': ('Bovista & Bromium', 'Bov. + Brom.', 'Bov & Brom', 'compound-ocr'),
    'thujvaler': ('Thuja occidentalis & Valeriana', 'Thuj. + Valer.', 'Thuj & Valer', 'compound-ocr'),
    'drosdulc': ('Drosera rotundifolia & Dulcamara', 'Dros. + Dulc.', 'Dros & Dulc', 'compound-ocr'),
    'cimiccocc': ('Cimicifuga racemosa & Cocculus indicus', 'Cimic. + Cocc.', 'Cimic & Cocc', 'compound-ocr'),
    'sposqu': ('Spongia tosta & Squilla maritima', 'Spong. + Squil.', 'Spong & Squil', 'compound-ocr'),
    'crotalfer': ('Crotalus horridus & Ferrum metallicum', 'Crot-h. + Ferr.', 'Crot-h & Ferr', 'compound-ocr'),
    'oleandop': ('Oleander & Opium', 'Oleand. + Op.', 'Oleand & Op', 'compound-ocr'),
    'asafasar': ('Asafoetida & Asarum europaeum', 'Asaf. + Asar.', 'Asaf & Asar', 'compound-ocr'),
    'concup': ('Conium maculatum & Cuprum metallicum', 'Con. + Cupr.', 'Con & Cupr', 'compound-ocr'),
    'arsasaf': ('Arsenicum album & Asafoetida', 'Ars. + Asaf.', 'Ars & Asaf', 'compound-ocr'),
    'brycalad': ('Bryonia alba & Caladium seguinum', 'Bry. + Calad.', 'Bry & Calad', 'compound-ocr'),
    'nuxvpetrol': ('Nux vomica & Petroleum', 'Nux-v. + Petr.', 'Nux-v & Petr', 'compound-ocr'),
    'parpetrol': ('Paris quadrifolia & Petroleum', 'Par. + Petr.', 'Par & Petr', 'compound-ocr'),
    'rheumrhodo': ('Rheum & Rhododendron chrysanthum', 'Rheum + Rhod.', 'Rheum & Rhod', 'compound-ocr'),
    'hellhep': ('Helleborus niger & Hepar sulphuris', 'Hell. + Hep.', 'Hell & Hep', 'compound-ocr'),
    'squstan': ('Squilla maritima & Stannum metallicum', 'Squil. + Stann.', 'Squil & Stann', 'compound-ocr'),
    'caustcic': ('Causticum & Cicuta virosa', 'Caust. + Cic.', 'Caust & Cic', 'compound-ocr'),
    'krelach': ('Kreosotum & Lachesis', 'Kreos. + Lach.', 'Kreos & Lach', 'compound-ocr'),
    'sabasabi': ('Sabadilla & Sabina', 'Sabad. + Sabin.', 'Sabad & Sabin', 'compound-ocr'),
    'hepign': ('Hepar sulphuris & Ignatia amara', 'Hep. + Ign.', 'Hep & Ign', 'compound-ocr'),
    'chamchel': ('Chamomilla & Chelidonium majus', 'Cham. + Chel.', 'Cham & Chel', 'compound-ocr'),
    'rhusruta': ('Rhus toxicodendron & Ruta graveolens', 'Rhus-t. + Ruta', 'Rhus-t & Ruta', 'compound-ocr'),
    'hepmerc': ('Hepar sulphuris & Mercurius solubilis', 'Hep. + Merc.', 'Hep & Merc', 'compound-ocr'),
    'brycact': ('Bryonia alba & Cactus grandiflorus', 'Bry. + Cact.', 'Bry & Cact', 'compound-ocr'),
    'strotar': ('Strontium carbonicum & Taraxacum', 'Stront-c. + Tarax.', 'Stront-c & Tarax', 'compound-ocr'),
    'sabisep': ('Sabina & Sepia', 'Sabin. + Sep.', 'Sabin & Sep', 'compound-ocr'),
    'caustcroc': ('Causticum & Crocus sativus', 'Caust. + Croc.', 'Caust & Croc', 'compound-ocr'),
    'chincic': ('Cinchona & Cicuta virosa', 'Chin. + Cic.', 'Chin & Cic', 'compound-ocr'),
    'staphsul': ('Staphysagria & Sulphur', 'Staph. + Sulph.', 'Staph & Sulph', 'compound-ocr'),
    'pbpod': ('Plumbum metallicum & Podophyllum', 'Plb. + Podo.', 'Plb & Podo', 'compound-ocr'),
    'asafbell': ('Asafoetida & Belladonna', 'Asaf. + Bell.', 'Asaf & Bell', 'compound-ocr'),
    'agaraloe': ('Agaricus & Aloe socotrina', 'Agar. + Aloe', 'Agar & Aloe', 'compound-ocr'),
    'bellbry': ('Belladonna & Bryonia alba', 'Bell. + Bry.', 'Bell & Bry', 'compound-ocr'),
    'mercphos': ('Mercurius solubilis & Phosphorus', 'Merc. + Phos.', 'Merc & Phos', 'compound-ocr'),
    'silspig': ('Silicea & Spigelia anthelmia', 'Sil. + Spig.', 'Sil & Spig', 'compound-ocr'),
    'santsars': ('Santoninum & Sarsaparilla', 'Sant. + Sars.', 'Sant & Sars', 'compound-ocr'),
    'aconaesc': ('Aconitum & Aesculus hippocastanum', 'Acon. + Aesc.', 'Acon & Aesc', 'compound-ocr'),
    'iodip': ('Iodum & Ipecacuanha', 'Iod. + Ip.', 'Iod & Ip', 'compound-ocr'),
    'agarasar': ('Agaricus & Asarum europaeum', 'Agar. + Asar.', 'Agar & Asar', 'compound-ocr'),
    'digdros': ('Digitalis & Drosera', 'Dig. + Dros.', 'Dig & Dros', 'compound-ocr'),
    'phospb': ('Phosphorus & Plumbum metallicum', 'Phos. + Plb.', 'Phos & Plb', 'compound-ocr'),
    'bovbry': ('Bovista & Bryonia alba', 'Bov. + Bry.', 'Bov & Bry', 'compound-ocr'),
    'platpb': ('Platinum & Plumbum metallicum', 'Plat. + Plb.', 'Plat & Plb', 'compound-ocr'),
    'phytplat': ('Phytolacca decandra & Platinum', 'Phyt. + Plat.', 'Phyt & Plat', 'compound-ocr'),
    'strosul': ('Strontium carbonicum & Sulphur', 'Stront-c. + Sulph.', 'Stront-c & Sulph', 'compound-ocr'),
    'stanstaph': ('Stannum & Staphysagria', 'Stann. + Staph.', 'Stann & Staph', 'compound-ocr'),
    'clemcocc': ('Clem & Cocculus indicus', 'Clem. + Cocc.', 'Clem & Cocc', 'compound-ocr'),
    'pulsrhus': ('Pulsatilla & Rhus toxicodendron', 'Puls. + Rhus-t.', 'Puls & Rhus-t', 'compound-ocr'),
    'absacon': ('Absinthium & Aconitum', 'Absin. + Acon.', 'Absin & Acon', 'compound-ocr'),
    'spigsqu': ('Spigelia & Squilla maritima', 'Spig. + Squil.', 'Spig & Squil', 'compound-ocr'),
    'petrolphos': ('Petroleum & Phosphorus', 'Petr. + Phos.', 'Petr & Phos', 'compound-ocr'),
    'tarthuj': ('Taraxacum & Thuja occidentalis', 'Tarax. + Thuj.', 'Tarax & Thuj', 'compound-ocr'),
    'spigstaph': ('Spigelia & Staphysagria', 'Spig. + Staph.', 'Spig & Staph', 'compound-ocr'),
    'glongraph': ('Glonoinum & Graphites', 'Glon. + Graph.', 'Glon & Graph', 'compound-ocr'),
    'mercrhus': ('Mercurius & Rhus toxicodendron', 'Merc. + Rhus-t.', 'Merc & Rhus-t', 'compound-ocr'),
    'stansul': ('Stannum & Sulphur', 'Stann. + Sulph.', 'Stann & Sulph', 'compound-ocr')
}

def load_remedy_master():
    """Build unified remedy master from core125, oorep, and TPB_ALIASES."""
    master = {}

    # 1. Base from oorep (2432 remedies)
    try:
        op = os.path.join(REFC, "oorep-remedies_by_abbrev.json")
        for ab, rec in json.load(open(op, encoding="utf-8")).items():
            k = nkey(ab)
            if k and k not in master:
                master[k] = {
                    'name': rec.get('name', ''),
                    'standard_abbrev': ab,
                    'common_name': rec.get('alt_names') or '',
                    'source': 'oorep(ref)'
                }
    except Exception as e:
        pass

    # 2. Override with core125 (PD authority for Boenninghausen core 125)
    try:
        sys.path.insert(0, TPB_DATA)
        import core125
        for _, ab, latin in core125.CORE_125:
            if ab:
                k = nkey(ab)
                master[k] = {
                    'name': latin,
                    'standard_abbrev': ab,
                    'common_name': '',
                    'source': 'core125(PD)'
                }
    except Exception as e:
        pass

    # 3. Add TPB aliases (historical print forms)
    for k, (latin, std_ab, common, src) in TPB_ALIASES.items():
        master[k] = {
            'name': latin,
            'standard_abbrev': std_ab,
            'common_name': common,
            'source': src
        }

    # 4. Add Compound tokens
    for k, (latin, std_ab, common, src) in COMPOUND_TOKENS.items():
        master[k] = {
            'name': latin,
            'standard_abbrev': std_ab,
            'common_name': common,
            'source': src
        }

    return master

MASTER = load_remedy_master()

def resolve_remedy(raw_remedy):
    """Resolve a raw printed remedy abbreviation to full Latin and metadata."""
    clean = re.sub(r"[,*().]", "", raw_remedy).strip()
    k = nkey(clean)

    if k in MASTER:
        res = MASTER[k].copy()
        res['norm'] = k
        res['raw_abbrev'] = clean
        return res

    # Check if raw_remedy has multiple words (e.g. 'Sep Sil')
    parts = clean.split()
    if len(parts) >= 2:
        part_matches = []
        for p in parts:
            pk = nkey(p)
            if pk in MASTER:
                part_matches.append(MASTER[pk]['name'])
        if len(part_matches) == len(parts):
            return {
                'name': ' & '.join(part_matches),
                'standard_abbrev': ' + '.join(parts),
                'common_name': 'Compound OCR token',
                'source': 'ocr-compound-resolved',
                'norm': k,
                'raw_abbrev': clean
            }

    # Fallback for unresolvable fragments
    return {
        'name': '',
        'standard_abbrev': clean,
        'common_name': '',
        'source': 'unmapped',
        'norm': k,
        'raw_abbrev': clean
    }

if __name__ == '__main__':
    # Test on rep_remedy.csv
    remedy_csv = os.path.join(ROOT, "out", "dataset", "final", "rep_remedy.csv")
    import csv
    with open(remedy_csv, encoding='utf-8-sig') as f:
        rems = list(csv.DictReader(f))

    mapped_count = 0
    total_tokens = sum(int(r['occurrences']) for r in rems)
    mapped_tokens = 0
    unmapped = []

    for r in rems:
        info = resolve_remedy(r['abbrev'])
        if info['name']:
            mapped_count += 1
            mapped_tokens += int(r['occurrences'])
        else:
            unmapped.append(r)

    print(f"Total remedies: {len(rems)}")
    print(f"Mapped remedies: {mapped_count}/{len(rems)} ({mapped_count*100/len(rems):.2f}%)")
    print(f"Mapped tokens  : {mapped_tokens}/{total_tokens} ({mapped_tokens*100/total_tokens:.4f}%)")
    print(f"Remaining unmapped remedies: {len(unmapped)}")
    if unmapped:
        print("Unmapped sample:")
        for u in unmapped[:15]:
            print(f"  {u['abbrev']:15s} (norm: {u['norm']:12s}) occurrences: {u['occurrences']}")
