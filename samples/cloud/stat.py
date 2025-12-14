from storix import AzureDataLake


fs = AzureDataLake()
fs.cd('file')
print(fs.pwd())
dir = fs.ls()
print(dir)
# print(fs.stat(dir[0]))
