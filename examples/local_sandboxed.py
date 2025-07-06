from storix import LocalFilesystem

fs = LocalFilesystem("/tmp/sandbox", sandboxed=True)
fs.touch("/secret.txt", "sandboxed!")
print(fs.ls("/"))  # ['secret.txt']
