import os

script_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(script_dir, "sample.txt")

with open(file_path, "r") as file:
    text = file.read().strip()

pattern = input("Enter search word: ")

print("\nSearch Result")
print("----------------")
found = False
for i in range(len(text) - len(pattern) + 1):
    if text[i:i + len(pattern)] == pattern:
        print("Pattern found at index", i)
        found = True

if not found:
    print("Pattern not found")
