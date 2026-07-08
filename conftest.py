# Keep the shipped plugin subtree free of bytecode caches.
#
# The suite in tests/ imports modules from plugins/planwise/scripts/. Without
# this flag CPython writes plugins/planwise/scripts/__pycache__/ next to those
# modules on import, and that directory would then be copied into the
# marketplace distribution — the plugin installer copies the working tree, not
# the git-tracked set, so .gitignore does not keep it out of the shipped
# artifact. Disabling bytecode writes closes that regeneration path.
import sys

sys.dont_write_bytecode = True
