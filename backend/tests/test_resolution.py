from app.graph.resolution import (
    EntityResolver, Mention, TextIndex, name_from_email, normalize_person, parse_header_people,
)


def people(*mentions):
    ms = [Mention(raw=m) if isinstance(m, str) else Mention(raw=m[0], email=m[1]) for m in mentions]
    return EntityResolver("person").build(ms)


def test_name_variants_collapse_into_one_person():
    r = people("Priya Sharma", "Priya", "Sharma, Priya", "priya sharma", "Dr. Priya Sharma")
    assert len(r.entities) == 1
    assert r.entities[0].name == "Priya Sharma"
    assert r.lookup("Priya") is r.lookup("Sharma, Priya") is r.entities[0]


def test_result_does_not_depend_on_mention_order():
    a = people("Priya", "Priya Sharma")
    b = people("Priya Sharma", "Priya")
    assert len(a.entities) == len(b.entities) == 1
    assert a.entities[0].name == b.entities[0].name == "Priya Sharma"


def test_ambiguous_first_name_is_not_guessed():
    r = people("Sam Lee", "Sam Patel", "Sam")
    assert len(r.entities) == 3
    assert r.lookup("Sam").name_only is True
    assert r.lookup("Sam") not in (r.lookup("Sam Lee"), r.lookup("Sam Patel"))


def test_similar_but_different_names_stay_separate():
    r = people("John Smith", "John Smyth")
    assert len(r.entities) == 2


def test_typo_is_merged():
    r = people("Priya Sharma", "Priyaa Sharma")
    assert len(r.entities) == 1


def test_middle_initial_merges_but_conflicting_emails_block_it():
    assert len(people("Priya K Sharma", "Priya Sharma").entities) == 1
    r = people(("Priya K Sharma", "a@x.com"), ("Priya Sharma", "b@y.com"))
    assert len(r.entities) == 2


def test_shared_email_merges_different_spellings():
    r = people(("Pri S", "priya@acme.com"), ("Priya Sharma", "priya@acme.com"))
    assert len(r.entities) == 1


def test_generic_names_are_dropped():
    r = people("team", "Everyone", "me", "Unknown")
    assert r.entities == []


def test_projects_merge_by_prefix_subset_but_not_across_distinct_projects():
    r = EntityResolver("project").build([Mention(raw=x) for x in
                                         ["Project Atlas", "Atlas", "Atlas migration", "Billing revamp", "Archive migration"]])
    names = sorted(e.name for e in r.entities)
    assert names == ["Archive migration", "Atlas migration", "Billing revamp"]
    assert r.lookup("Project Atlas") is r.lookup("Atlas migration")


def test_ambiguous_single_token_project_not_merged():
    r = EntityResolver("project").build([Mention(raw=x) for x in ["Atlas migration", "Data migration", "migration"]])
    assert len(r.entities) == 3


def test_header_parsing_handles_quoted_commas_and_drops_system_senders():
    got = parse_header_people({
        "from": '"Sharma, Priya" <priya.sharma@acme.com>',
        "to": ['"Doe', ' John" <john@acme.com>', " Noreply <no-reply@vendor.com>", " bare@acme.com"],
    })
    names = {g["email"]: g["name"] for g in got}
    assert names["priya.sharma@acme.com"] == "Priya Sharma"
    assert names["john@acme.com"] == "John Doe"
    assert "no-reply@vendor.com" not in names
    assert names["bare@acme.com"] == "Bare"


def test_name_from_email():
    assert name_from_email("priya.sharma@acme.com") == "Priya Sharma"
    assert name_from_email("noreply@acme.com") is None
    assert normalize_person('"Sharma, Priya" <p@x.com>') == "priya sharma"


def test_text_index_collapses_near_duplicates_only():
    idx = TextIndex()
    idx.add("Move forward with the phased rollout instead of a big-bang cutover", "A")
    assert idx.find("Move forward with the phased rollout instead of a big-bang cutover for Atlas") == "A"
    assert idx.find("Choose Vendor B for the logging pipeline") is None
