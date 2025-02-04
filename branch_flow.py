# These global variables need adjustment
llm_selector_height = 57
spacer_size = 10
# Remove this line since interface_height should be the TOTAL height including input
# interface_height = config.height - llm_selector_height - spacer_size

# In create_flow method
interface_view = flow['chat_interface'].create_interface_view(
    input_height=110,
    # Pass the full remaining height after subtracting selector and spacer
    height=config.height - llm_selector_height - spacer_size
)

view = pn.Column(
    model_selector_view,
    pn.Spacer(height=spacer_size),
    interface_view,
    name=tab_name,
    sizing_mode='stretch_width'  # This ensures the column takes full width
) 