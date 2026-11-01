# GitHub पर Folio अपलोड करना

वेबसाइट: [ThinkHomeo.in](https://thinkhomeo.in/)

## तैयार फाइलें

- `README.md`: ऐप का परिचय, installation, उपयोग और developer checks।
- `.gitignore`: स्थानीय documents, scans, logs, environments और models बाहर रखता है।
- `.gitattributes`: code और Windows launcher की line endings व्यवस्थित रखता है।
- `.github/workflows/checks.yml`: push/PR पर Python और UI checks चलाता है।
- `NOTICE.md`: attribution और अभी तक license चुना न होने की स्थिति।
- `dist/folio-ocr-studio-github.zip`: साफ़ source ZIP।
- `dist/folio-ocr-studio-github.manifest.json`: शामिल फाइलें और उनके SHA-256 hashes।

ZIP में ऐप चलाने का source है। इसमें आपके saved documents, database,
स्कैन, logs, `.venv`, language packs और model binaries नहीं हैं। Text OCR
के लिए models आवश्यक नहीं हैं; dependencies Setup से install होंगी।

## तरीका 1: GitHub वेबसाइट से

1. GitHub पर sign in करें और **New repository** खोलें।
2. सुझाया नाम: **folio-ocr-studio**। Visibility अपनी आवश्यकता के अनुसार चुनें।
3. Description: **Local OCR studio for English and Hindi scans, document review and export by ThinkHomeo.in.**
4. Existing files upload करने के लिए repository बनाते समय अतिरिक्त README,
   license या `.gitignore` न जोड़ें; ये तैयार source में मौजूद हैं। License
   चुनने पर उसे बाद में अलग से जोड़ सकते हैं।
5. तैयार ZIP extract करें। उसके **folio-ocr-studio** folder के अंदर की files
   और folders को **Add file → Upload files** में चुनें और commit करें। ZIP को
   अकेले upload करने से GitHub source repository नहीं बनेगी।
6. Dot files भी शामिल हों: `.gitignore`, `.gitattributes` और `.github/`।
   यदि browser upload में छूटें, Git वाला तरीका इस्तेमाल करें।
7. Repository के **About** में Website **https://thinkhomeo.in/** जोड़ें।
   उपयोगी topics: `ocr`, `tesseract`, `hindi`, `document-review`, `python`, `fastapi`।
8. **Actions** tab में checks का परिणाम देखें।

## तरीका 2: Git से

नीचे दिए commands इस परियोजना के folder में चलाएँ, पूरे parent website
folder में नहीं। पहले अपना Git commit नाम और GitHub का verified/noreply
email configure करें। `YOUR-ACCOUNT` को अपने GitHub username से बदलें।
यदि repository के लिए दूसरा नाम चुना है, URL में उसे भी बदलें।

```powershell
git init -b main
git config user.name "YOUR-NAME"
git config user.email "YOUR-VERIFIED-OR-NOREPLY-EMAIL"
git add .
git status --short
git commit -m "Prepare Folio OCR Studio for GitHub"
git remote add origin https://github.com/YOUR-ACCOUNT/folio-ocr-studio.git
git push -u origin main
```

यदि स्थानीय Git repository पहले से बनाई हुई है, `git init` दोबारा न चलाएँ।
Login Git/GitHub के अपने authentication dialog से करें। Source files में
password या access token लिखने की आवश्यकता नहीं है।

## ZIP दोबारा बनाना

Code बदलने के बाद project folder से चलाएँ:

```powershell
python tools/prepare_github.py
```

Script केवल चुने हुए source folders/files जोड़ता है और obvious credential
patterns, personal Windows paths, symlinks तथा बड़ी files की जाँच करता है।
Manifest में हर शामिल file का path, size और SHA-256 मिलता है। ZIP और manifest
`dist/` में बनते हैं; यह folder Git में शामिल नहीं होता।

## GitHub और ऐप चलाना

GitHub source code साझा करता है। GitHub Pages इस Python OCR server को नहीं
चला सकता। दूसरे computer पर repository download/extract करके
**setup_folio.bat** चलाना होगा। Detailed instructions [README.md](../README.md)
और [APPLICATION.md](../APPLICATION.md) में हैं।
