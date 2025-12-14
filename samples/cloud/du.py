from storix import AzureDataLake


fs = AzureDataLake()
dir = fs.ls()
fs.cd(dir[0])

it = (f for f in fs.ls(abs=True) if f.maybe_file())
first = next(it)
print(first)
print(fs.du(first))
