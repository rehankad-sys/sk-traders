# 📱 SK Traders - 100% Offline Android Mobile App (.apk)

यह **SK TRADERS** का कम्प्लीट ऑफलाइन Android मोबाइल ऐप प्रोजेक्ट है। इसमें आपके PC सॉफ्टवेयर का पूरा डेटाबेस, लेजर हिस्ट्री, Gemini 3.8 Flash वॉइस AI, और Google Drive बैकअप सिंक इंटीग्रेटेड है।

---

## 🚀 मुख्य फीचर्स (Key Features)

1. **Pre-Loaded Offline SQLite Database (`accounting_data.db`):**
   - आपके मौजूदा डेटाबेस की सभी 1,830+ कस्टमर फाइल्स और ₹7,62,387 का बैलेंस ऐप के अंदर `assets/accounting_data.db` में पैक है।
   - मोबाइल में ऐप बिना इंटरनेट (Flight Mode) में भी पहली बार खुलेगा, तो यह डेटाबेस फोन की लोकल स्टोरेज में कॉपी हो जाएगा और तुरंत सारे ग्राहक ऑफलाइन दिखेंगे।

2. **Modern Mobile Touch UI (Material 3 Mobile Design):**
   - **Home Screen:**
     - सबसे ऊपर **कुल ग्राहक (1,822)** और **कुल मार्केट बाकी उधार (₹ 7,56,147)** का लाइव कार्ड।
     - सिंगल स्मार्ट सर्च बार (सभी | नाम | पता | मोबाइल फिल्टर्स के साथ)।
     - टच-फ्रेंडली कस्टमर लिस्ट (अवतार इनिशियल, मोबाइल नंबर, शहर और लाल/हरे रंग का बाकी/चुकता बैलेंस बैज)।
   - **Customer Action & Khata Ledger:**
     - ग्राहक पर टैप करते ही उसका खाता खुलता है।
     - ऊपर बड़े टच बटन: **`+ Debit (उधार)`**, **`+ Credit (जमा)`**, और **`✏ Edit Profile`**।
   - **Entry Edit Popup (लेजर एंट्री संपादन):**
     - हिस्ट्री की किसी भी डेबिट/क्रेडिट एंट्री पर टैप करने पर एक पॉपअप खुलता है जहाँ से उस एंट्री की **Amount, Date, Due Date और Memo** को एडिट या डिलीट किया जा सकता है।

3. **Gemini 3.8 Flash Voice AI (Mobile Mic):**
   - स्क्रीन पर नीचे फ्लोटिंग **`🎤 बोलकर एंट्री`** बटन।
   - आवाज़ में बोलने पर (उदा: *"राहुल को 5000 का माल उधार दिया आज"*) यह सीधे `gemini-3.8-flash` REST API (`temperature=0.0`, `thinkingBudget=0`) से प्रोसेस होकर रियल-टाइम में खाते में सेव हो जाती है।

4. **Gmail (Google Drive) & Local Backup:**
   - PC सॉफ्टवेयर वाली सेम बैकअप फाइल `Accounting_Software_Cloud_Backup.db` को Google Drive से अपलोड / रिस्टोर करने का विकल्प।
   - ऑफलाइन शेयरिंग के लिए सीधे फोन से `accounting_data.db` को WhatsApp या फाइल्स में Export करने की सुविधा।

---

## 🛠️ .apk फाइल कैसे जनरेट करें (How to Generate .apk)

### Option 1: GitHub Actions (1-Click Auto-Builder - बिना किसी लोकल SDK के):
यदि आपके लोकल कंप्यूटर पर Android SDK / Flutter नहीं है, तो GitHub Actions आपके लिए क्लाउड पर फ्री में स्टैंडअलोन `.apk` बिल्ड कर देगा:
1. इस प्रोजेक्ट को अपने **GitHub Repository** में Push करें।
2. GitHub पर अपने प्रोजेक्ट के **Actions** टैब में जाएं।
3. बाईं तरफ **"Build SK Traders Android APK"** वर्कफ्लो पर क्लिक करें।
4. **"Run workflow"** बटन दबाएं।
5. 3 से 4 मिनट में बिल्ड पूरा हो जाएगा और **Artifacts** सेक्शन में आपको सीधे **`SK_Traders_Accounting.apk`** डाउनलोड के लिए मिल जाएगी!

### Option 2: लोकल पीसी पर टेस्ट व रन करना (Preview on PC):
- **`run_mobile_preview.bat`** पर डबल-क्लिक करें:
  - यह मोबाइल ऐप को आपके पीसी पर फोन-साइज विंडो में लाइव चला देगा।
- **`run_mobile_web.bat`** पर डबल-क्लिक करें:
  - यह मोबाइल टच वेब व्यू को ब्राउज़र में खोल देगा।

---

## 📁 फोल्डर संरचना (Folder Structure):
```
SK_Traders_Android_App/
│── assets/
│   └── accounting_data.db        (1,830 कस्टमर्स वाला प्री-लोडेड डेटाबेस)
│── www/                          (Cordova/Web touch app)
│   ├── index.html
│   └── data/initial_data.json
│── main.py                       (Flet/Flutter Android App का मुख्य कोड)
│── flet.toml                     (Android पैकेज व परमिशन सेटिंग्स)
│── requirements.txt              (Python डिपेंडेंसीज)
│── run_mobile_preview.bat        (पीसी पर मोबाइल ऐप प्रीव्यू लॉन्चर)
│── run_mobile_web.bat            (ब्राउज़र में मोबाइल वेब लॉन्चर)
│── build_apk_locally.bat         (लोकल APK बिल्डर स्क्रिप्ट)
└── README.md                     (यह गाइड)

.github/workflows/
└── build_apk.yml                 (GitHub Actions स्टैंडअलोन APK ऑटो-बिल्डर)
```
