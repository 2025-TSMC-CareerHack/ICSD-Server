import deepl

class DeeplTranslator:
    def read_glossary_from_csv(self, file_path):
        glossary = {}
        with open(file_path, mode="r", encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines:
                source, target = line.strip().split(",")
                glossary[source] = target
        return glossary
    def __init__(self, auth_key):
        self.translator = deepl.Translator(auth_key)
        # Create a en glossary
        self.en_glossary_name = "EN Glossary"
        source_lang = "EN"
        target_lang = "ZH-HANT"
        self.en_glossary_entries = self.read_glossary_from_csv("./translate/EN_2_ZH_glossary.csv")

        self.en_glossary = self.translator.create_glossary(self.en_glossary_name, source_lang, target_lang, self.en_glossary_entries)


        # Create a ja glossary
        self.ja_glossary_name = "JA Glossary"
        source_lang = "JA"
        self.ja_glossary_entries = self.read_glossary_from_csv("./translate/JA_2_ZH_glossary.csv")

        self.ja_glossary = self.translator.create_glossary(self.ja_glossary_name, source_lang, target_lang, self.ja_glossary_entries)


        # Create a en glossary
        self.de_glossary_name = "DE Glossary"
        source_lang = "EN"
        self.de_glossary_entries = self.read_glossary_from_csv("./translate/DE_2_ZH_glossary.csv")

        self.de_glossary = self.translator.create_glossary(self.de_glossary_name, source_lang, target_lang, self.de_glossary_entries)


    def translate_to_chinese(self, text, source_lang):
        print(f"Translating text: {text}", source_lang)
        if source_lang not in ["EN", "JA", "DE"]:
            raise ValueError("Source languagself.e must be 'EN', 'JA', or 'DE'")
        
        if source_lang == "EN":
            glossary = self.en_glossary
        elif source_lang == "JA":
            glossary = self.ja_glossary
        elif source_lang == "DE":
            glossary = self.de_glossary
            
        result = self.translator.translate_text(text, source_lang=source_lang, target_lang="ZH-HANT", glossary=glossary, model_type="prefer_quality_optimized")
        return result.text

    # Example usage
    # translated_text = translate_to_chinese("Hello everyone, today we are going to discuss the issue regarding DDR Ratio. It was found that the ratio on DP is quite high this week. Does Martin know the reason?", "EN")
    # print(translated_text)  # "你好，世界！"
    
if __name__ == "__main__":
    translator = DeeplTranslator(auth_key)
    translated_text = translator.translate_to_chinese("Hello everyone, today we are going to discuss the issue regarding DDR Ratio. It was found that the ratio on DP is quite high this week. Does Martin know the reason?", "EN")
    print(translated_text)  # "你好，世界！"