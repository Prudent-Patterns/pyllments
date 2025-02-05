from importlib.resources import files

def get_asset(*path_segments: str, as_string: bool = False) -> str:
    """
    Get an asset either as a filesystem path or as a string content.

    Parameters
    ----------
    *path_segments : str
        One or more path segments to the asset.
        Examples:
            ('assets', 'css', 'global.css')
            or a single string "assets/css/global.css" which will be split internally.
    as_string : bool, default False
        If True, returns the file contents as a string.
        If False, returns the filesystem path to the file.

    Returns
    -------
    str
        Either the file contents or the absolute path to the file.
    """
    # If a single string is provided that contains path separators ('/'),
    # split it into segments.
    if len(path_segments) == 1 and '/' in path_segments[0]:
        path_segments = tuple(path_segments[0].split('/'))
    
    # Use importlib.resources to locate the resource within the 'pyllments' package.
    resource = files('pyllments').joinpath(*path_segments)
    
    if as_string:
        return resource.read_text()
    else:
        # Use as_file to provide a file-system path, which may be necessary for APIs that require a path.
        from importlib.resources import as_file
        with as_file(resource) as asset_path:
            return str(asset_path)
