from storix import LocalFilesystem


fs = LocalFilesystem()
it = (f for f in fs.ls(abs=True) if f.maybe_file())
first = next(it)
print(first)
print(fs.du(first))
