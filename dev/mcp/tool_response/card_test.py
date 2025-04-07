import panel as pn


card1 = pn.layout.Card(pn.pane.Markdown("""
Lorem ipsum dolor sit amet, consectetur adipiscing elit. 
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. 
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. 
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. 
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
"""), title="Card 1")

card2 = pn.layout.Card(pn.pane.Markdown("""
In a world where technology and nature coexist, 
the balance between innovation and preservation becomes crucial. 
As we advance into the future, we must remember the lessons of the past, 
embracing sustainable practices that honor our planet. 
Together, we can forge a path that respects both progress and the environment, 
ensuring a brighter tomorrow for generations to come.
"""), title="Card 2")

pn.Column(card1, card2, height=200, width=400, styles={'overflow': 'auto'}).servable()