"""Author data, shared by the Home tab, help texts and reports."""
FACULTY = "Facultad de Ingeniería y Ciencias"
UNIVERSITY = "Universidad Autónoma de Tamaulipas"

AUTHOR = {
    "name": "Daniel Ibarra-Marinas",
    "faculty": FACULTY,
    "university": UNIVERSITY,
    "email": "daniel.ibarra@uat.edu.mx",
    "orcid": "0000-0003-3683-4456",
    "github": "adanielibarra",
    "scholar": "https://scholar.google.com/citations?user=5JgVP2MAAAAJ&hl=en",
    "researchgate": "https://www.researchgate.net/profile/Daniel-Ibarra-Marinas",
}
AUTHOR["affiliation"] = f"{FACULTY}, {UNIVERSITY}"
COAUTHORS = [
    {"name": "Alejandro Fenollar-Rueda", "orcid": "0009-0005-4229-8778", "affiliation": "Universidad de Alicante"},
    {"name": "Ana Mónica de Jhesú García-García", "orcid": "0000-0001-6613-6945", "affiliation": f"{FACULTY}, {UNIVERSITY}"},
    {"name": "Ángela Bellido-Solano", "affiliation": "Universidad Complutense de Madrid"},
    {"name": "Dulce Mata-Chacón", "orcid": "0000-0003-3294-8210", "affiliation": "Instituto Español de Oceanografía (IEO-CSIC)"},
    {"name": "Marta Serrano-Vicente", "affiliation": "Universidad de Murcia"},
    {"name": "Arturo Mora-Olivo", "orcid": "0000-0002-9654-0305", "affiliation": f"{FACULTY}, {UNIVERSITY}"},
]
NAMES = [AUTHOR["name"]] + [c["name"] for c in COAUTHORS]
AUTHORS_TEXT = ", ".join(NAMES[:-1]) + " and " + NAMES[-1]
CREDIT = f"GLUB, by {AUTHORS_TEXT}. Contact: {AUTHOR['email']} ({FACULTY}, {UNIVERSITY})."
