# run_pipeline.py
import subprocess

steps = [
    ("Scraping data", "python scrape_aep.py"),
    ("Preprocessing JSON → CSV", "python preprocess_aep.py"),
    ("Uploading to MongoDB", "python upload_to_mongo.py"),
]

for desc, cmd in steps:
    print(f"\n🔹 {desc} ...")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f" Error during: {desc}")
        break
else:
    print("\n Pipeline completed successfully!")
