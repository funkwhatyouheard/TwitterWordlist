import csv
from os import listdir, path

csvDir = input("Enter the path to the directory containing the wordlists:\n")
filenames = listdir(csvDir)
files = [path.join(csvDir,name) for name in filenames]
wordlist = dict()

for file in files:
    with open(file,"r",encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Word'] not in wordlist.keys():
                wordlist[row['Word']] = int(row['Occurences'])
            else:
                wordlist[row['Word']] = int(wordlist[row['Word']]) + int(row['Occurences'])

# sort them in descending order by occurence and create list for writing
wordlist = {key: val for key, val in sorted(wordlist.items(), key = lambda ele: ele[1], reverse = True)}
aggregate = [dict(Word=k,Occurrences=v) for k, v in wordlist.items()]

with open(path.join(csvDir,"Aggregate.csv"),"w",encoding='utf-8',newline='') as file:
    writer = csv.DictWriter(file,fieldnames=aggregate[0].keys())
    writer.writeheader()
    writer.writerows(aggregate)

with open(path.join(csvDir,"Aggregate.txt"),"w",encoding='utf-8') as file:
    file.write("\n".join([w['Word'] for w in aggregate]))