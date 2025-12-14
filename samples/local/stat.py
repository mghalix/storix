from storix import LocalFilesystem


fs = LocalFilesystem()
print(fs.pwd())
dir = fs.ls()
print(fs.stat(dir[0]))
