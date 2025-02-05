def create_model_selector_view(self, models, provider: str = None, model: str = None):
    """
    Creates the model selector view using the 'models' parameter.
    
    If 'models' is a dictionary:
      - Each key is used as the display name.
      - Each value should be either a string (display name and model spec are identical) or a dictionary with a "model" key.
    If 'models' is a list:
      - It is converted into a dictionary mapping each element to itself.
    
    The UI displays the friendly display name while the underlying value returned is the actual model identifier.
    
    Parameters
    ----------
    models : dict or list
        Custom models configuration.
    provider : str, optional
        Initial provider value.
    model : str, optional
        Initial model identifier.
    
    Returns
    -------
    pn.Row
        A Panel Row containing a provider selector and a model selector widget.
    
    Raises
    ------
    ValueError
        If a dictionary entry is encountered without a "model" key.
    TypeError
        If models is not a list or a dictionary.
    """
    # Convert list to dictionary mapping each element to itself.
    if isinstance(models, list):
        options = {m: m for m in models}
    elif isinstance(models, dict):
        options = {}
        for display_name, model_info in models.items():
            if isinstance(model_info, dict):
                if "model" not in model_info:
                    raise ValueError(
                        f"Custom model configuration for '{display_name}' must have a 'model' key."
                    )
                options[display_name] = model_info["model"]
            else:
                options[display_name] = model_info
    else:
        raise TypeError("models must be either a list or a dictionary.")
    
    # Construct providers from the model specifications.
    providers = {spec.split("/")[0] for spec in options.values() if isinstance(spec, str) and "/" in spec}
    provider_select = pn.widgets.Select(name="Provider", options=list(providers))
    
    # Create the model select widget using the mapping.
    model_select = pn.widgets.Select(name="Model", options=options)
    
    # Set initial widget values if provided.
    if provider and provider in provider_select.options:
        provider_select.value = provider
    if model and model in options.values():
        model_select.value = model

    return pn.Row(provider_select, model_select)