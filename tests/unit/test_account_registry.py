from backend.core.account_registry import AccountRegistry, lookup_deletion

SAMPLE = [
    {
        "name": "Spotify",
        "url": "https://support.spotify.com/close-account",
        "difficulty": "medium",
        "notes": "Close your account from the support page.",
        "domains": ["spotify.com", "accounts.spotify.com", "open.spotify.com"],
    },
    {
        "name": "Bitly",
        "url": "https://bitly.com/pages/privacy",
        "difficulty": "hard",
        "notes": "Contact support to delete.",
        "domains": ["bit.ly", "bitly.com"],
    },
    {
        "name": "4PDA",
        "url": "https://4pda.to/forum/",
        "difficulty": "impossible",
        "notes": "It is not possible to delete your account.",
        "domains": ["4pda.ru", "4pda.to"],
    },
]


def test_lookup_by_exact_domain():
    reg = AccountRegistry(SAMPLE)
    hit = reg.lookup(url="https://bit.ly/abc")
    assert hit is not None
    assert hit.name == "Bitly"
    assert hit.difficulty == "hard"


def test_lookup_strips_subdomain_to_registrable():
    reg = AccountRegistry(SAMPLE)
    # open.spotify.com is present, but a deeper/unknown subdomain must still resolve
    hit = reg.lookup(url="https://player.open.spotify.com/user/x")
    assert hit is not None and hit.name == "Spotify"


def test_lookup_by_name_fallback_normalizes_punctuation():
    reg = AccountRegistry(SAMPLE)
    # scanner emits "Bit.ly"; dataset name is "Bitly"
    hit = reg.lookup(name="Bit.ly")
    assert hit is not None and hit.name == "Bitly"


def test_impossible_flag():
    reg = AccountRegistry(SAMPLE)
    hit = reg.lookup(url="https://4pda.to/forum/index.php")
    assert hit is not None and hit.impossible is True


def test_no_match_returns_none():
    reg = AccountRegistry(SAMPLE)
    assert reg.lookup(url="https://nonexistent-service-xyz.example/x") is None
    assert reg.lookup(name="TotallyUnknownService999") is None


def test_url_takes_precedence_over_name():
    reg = AccountRegistry(SAMPLE)
    # url resolves Spotify even if a bogus name is passed
    hit = reg.lookup(url="https://open.spotify.com/x", name="Bitly")
    assert hit.name == "Spotify"


def test_load_real_dataset_resolves_github():
    reg = AccountRegistry.load()
    hit = reg.lookup(url="https://github.com/soxoj")
    assert hit is not None
    assert hit.name == "GitHub"
    assert hit.url.startswith("http")


def test_module_level_lookup_singleton():
    assert lookup_deletion(url="https://github.com/x") is not None
