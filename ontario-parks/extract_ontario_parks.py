import urllib.request
import json
import re
from bs4 import BeautifulSoup

def main():
    url = "https://en.wikipedia.org/wiki/List_of_provincial_parks_in_Ontario"
    print("Fetching Wikipedia list of provincial parks...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read()
            
        soup = BeautifulSoup(html, "html.parser")
        parks = set()
        
        # Look for text matching "Provincial Park" in links or table cells
        for a in soup.find_all("a", href=True):
            text = a.get_text().strip()
            # Clean up the name (e.g. "Algonquin Provincial Park" -> "Algonquin")
            if "Provincial Park" in text:
                park_name = text.split("Provincial Park")[0].strip()
                if park_name and len(park_name) > 2 and not any(k in park_name.lower() for k in ["list", "category", "wikipedia"]):
                    parks.add(park_name)
                    
        # Fallback list of common/popular parks in case of scrap block or network issue
        common_parks = [
            "Algonquin", "Arrowhead", "Awenda", "Balsam Lake", "Bass Lake", 
            "Blue Lake", "Bon Echo", "Bonheur River", "Bronte Creek", 
            "Craigleith", "Darlington", "Driftwood", "Earl Rowe", "Emily", 
            "Fushimi Lake", "Inverhuron", "Ivanhoe Lake", "Kettle Lakes", 
            "Killbear", "Lake Superior", "Long Point", "MacGregor Point", 
            "Marten River", "McRae Point", "Mikisew", "Murphys Point", 
            "Oastler Lake", "Pancake Bay", "Pinery", "Point Farms", 
            "Port Bruce", "Presqu'ile", "Quetico", "Restoule", "Rondeau", 
            "Rushing River", "Samuel de Champlain", "Sandbanks", 
            "Sauble Falls", "Selkirk", "Sibbald Point", "Silent Lake", 
            "Silver Lake", "St. Joseph Island", "Turkey Point", 
            "Wasaga Beach", "Wheatley", "Windy Lake"
        ]
        
        for p in common_parks:
            parks.add(p)
            
        sorted_parks = sorted(list(parks))
        print(f"Extracted {len(sorted_parks)} provincial parks.")
        
        out_path = "all_parks.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(sorted_parks, f, indent=4)
        print(f"Saved to {out_path}.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
