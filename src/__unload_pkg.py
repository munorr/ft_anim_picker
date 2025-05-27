import sys
import os

def unload(pkg):
    pkg_dir = os.path.abspath(os.path.dirname(pkg.__file__))
    #print("dir is {}".format(pkg_dir))

    def _is_part_of_pkg(module_):
        mod_path = getattr(module_, "__file__", os.sep)

        if mod_path is not None:
            mod_dir = os.path.abspath(os.path.dirname(mod_path))
        else:
            return None

        return mod_dir.startswith(pkg_dir)

    to_unload = [name for name, module in sys.modules.items() if _is_part_of_pkg(module)]

    for name in to_unload:
        sys.modules.pop(name)
        #print("Unloaded {}.".format(name))
print("-----------------------------------------------------------")