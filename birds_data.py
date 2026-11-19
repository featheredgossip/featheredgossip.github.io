# -*- coding: utf-8 -*-
"""Spisak ptica sa tačnim šarama (isti kao u botu za dizajne) i sezone.
region: uk = Britanija/Evropa, na = Severna Amerika, both = oba, world = egzotične/omiljene ptice birdera."""

SEASONS = [
    ("halloween", "Halloween (spooky-cute: pumpkins, bats, witch hats)", (8, 15), (10, 5)),
    ("thanksgiving", "Thanksgiving / autumn (pumpkin pie, leaves, gratitude)", (9, 10), (10, 20)),
    ("christmas", "Christmas / winter holidays (santa hats, cozy sweaters, candy canes, wrapped gifts)", (9, 15), (12, 5)),
    ("valentines", "Valentine's Day (hearts, love, friendship, anti-valentine humor)", (12, 15), (1, 25)),
    ("spring-easter", "Spring / Easter (flowers, bunny ears, eggs)", (2, 10), (3, 25)),
    ("mothers-day", "Mother's Day (gift for mom, flowers, hugs)", (3, 15), (4, 25)),
    ("fathers-day", "Father's Day (gift for dad, grill, fishing, dad jokes)", (4, 25), (5, 31)),
    ("summer", "Summer / vacation (sunglasses, ice cream, beach)", (3, 25), (5, 31)),
    ("back-to-school", "Back to school (backpacks, books, pencils)", (6, 10), (7, 25)),
]


def _b(region, palette, marks, seasons=()):
    return {"region": region, "palette": set(palette), "marks": marks, "seasons": list(seasons)}


BIRDS = {
    # --- Britanija / Evropa ---
    "european robin": _b("uk", [], "olive-brown crown, back, wings and tail; bright orange-red face and breast edged with a "
                         "thin blue-grey border; off-white belly; big black eye; thin dark bill; slim brown legs", ["christmas"]),
    "blue tit": _b("uk", ["blue", "green"], "bright blue cap, wings and tail; white cheeks; thin dark navy line through the "
                   "eye; dark navy collar line around the cheek and a small dark bib; lemon-yellow belly; yellow-green back; "
                   "one white wing bar; tiny dark bill"),
    "great tit": _b("uk", ["blue", "green"], "glossy black head and neck with big white cheek patches; yellow belly with a "
                    "bold black stripe down the middle of the breast; olive-green back; blue-grey wings with one white wing "
                    "bar; small dark bill"),
    "long-tailed tit": _b("uk", ["pink"], "tiny round fluffy body with a very long thin black-and-white tail; white head with "
                          "a broad black stripe above each eye; black back; dusky-pink shoulders and flanks; whitish breast; "
                          "tiny stubby black bill", ["christmas"]),
    "coal tit": _b("uk", [], "small bird with a black cap and black bib; white cheeks; white patch on the back of the neck; "
                   "grey back; buff-white belly; two white wing bars; tiny dark bill"),
    "european goldfinch": _b("uk", [], "bright red face mask; white cheeks and throat; black crown and nape; warm buff-brown "
                             "back and flanks; black wings with a broad bright yellow wing bar; black tail with white spots; "
                             "pale pointed bill", ["spring-easter"]),
    "bullfinch": _b("uk", ["pink", "blue"], "chunky male with a glossy black cap and chin; rosy-pink cheeks and breast; "
                    "blue-grey back; black wings with one pale grey-white wing bar; white rump; black tail; short thick black "
                    "bill", ["christmas"]),
    "chaffinch": _b("uk", ["pink", "blue"], "male with a blue-grey cap and nape; rusty-pink face and breast; chestnut-brown "
                    "back; olive rump; black wings with two bold white wing bars; white outer tail feathers; grey bill"),
    "house sparrow": _b("both", [], "male with a grey crown; chestnut-brown stripe behind the eye and on the nape; black bib; "
                        "pale grey cheeks and belly; brown back streaked with black; one white wing bar; short thick dark bill"),
    "common starling": _b("both", ["pink", "green"], "glossy black body with an oily green-and-purple sheen and small white "
                          "star-like spots; pointed yellow bill; reddish legs"),
    "common blackbird": _b("uk", [], "male entirely glossy black; bright orange-yellow bill and yellow eye-ring; dark legs; "
                           "fairly long tail"),
    "wren": _b("uk", [], "tiny round warm-brown bird; fine dark barring on the wings and tail; short tail cocked straight up; "
               "pale cream eyebrow stripe; paler buff belly; thin slightly curved bill"),
    "magpie": _b("uk", ["blue", "green"], "black head, breast and back; bright white belly and white shoulder patches; very "
                 "long black tail with a blue-green gloss; black wings with a blue sheen; strong black bill"),
    "eurasian jay": _b("uk", ["pink", "blue"], "pinkish-brown body; pale crown streaked with black; bold black moustache "
                       "stripe; white throat; bright blue-and-black barred patch on the wing; black wings and tail; white "
                       "rump; pale eye"),
    "common kingfisher": _b("uk", ["blue", "green"], "electric blue-turquoise back, crown and wings; bright orange cheeks and "
                            "belly; white throat and a white patch on the side of the neck; long dagger-shaped black bill; "
                            "tiny bright red legs"),
    "goldcrest": _b("uk", ["green"], "tiny round olive-green bird; bright yellow crown stripe bordered with black; plain pale "
                    "face with a big black eye; two white wing bars; very thin dark bill", ["christmas"]),
    "eurasian nuthatch": _b("uk", ["blue"], "blue-grey back and crown; long black stripe through the eye; white cheeks and "
                            "throat; warm orange-buff belly; chestnut flanks; strong pointed dark bill; short tail"),
    "great spotted woodpecker": _b("uk", [], "black-and-white pied pattern; large white oval shoulder patches; white cheeks "
                                   "crossed by black lines; bright red patch under the tail; small red patch on the back of "
                                   "the head; strong chisel bill"),
    "tawny owl": _b("uk", [], "round head with no ear tufts; mottled rusty-brown body with darker streaks; pale facial disc "
                    "outlined in brown; big dark eyes", ["halloween"]),
    "grey heron": _b("uk", [], "tall grey wader; white head and neck; black stripe from the eye to long black head plumes; "
                     "black streaks down the front of the neck; long yellow-orange dagger bill; grey back; long yellowish legs"),
    "pied wagtail": _b("uk", [], "slim black-and-white bird; black crown, back and bib; white face and belly; white wing bars; "
                       "long black tail with white edges; thin black bill"),
    "jackdaw": _b("uk", [], "small black crow; soft grey nape and sides of the head; pale silvery-white eye; short black bill",
                  ["halloween"]),
    # --- Severna Amerika ---
    "american robin": _b("na", [], "dark grey-brown back; brick-orange breast; blackish head with broken white eye-ring; "
                         "yellow bill; white patch under the tail", ["spring-easter"]),
    "northern cardinal": _b("na", [], "male bright red all over; tall pointed red crest; black face mask around a thick "
                            "orange-red cone-shaped bill", ["christmas"]),
    "blue jay": _b("na", ["blue"], "bright blue crest, back, wings and tail; black necklace collar; white face and pale "
                   "grey-white belly; wings and tail barred with black and white; black bill"),
    "black-capped chickadee": _b("na", [], "black cap and black bib; bright white cheeks; soft grey back; white belly with "
                                 "warm buff flanks; tiny black bill", ["christmas"]),
    "american goldfinch": _b("na", [], "male bright lemon-yellow body; black forehead cap; black wings with white wing bars; "
                             "black-and-white tail; small orange cone-shaped bill", ["spring-easter", "summer"]),
    "eastern bluebird": _b("na", ["blue"], "bright royal-blue head, back, wings and tail; rusty-orange throat and breast; "
                           "white belly; small dark bill", ["spring-easter"]),
    "ruby-throated hummingbird": _b("na", ["green"], "tiny bird with a glossy green back and crown; glowing ruby-red throat; "
                                    "white collar and pale belly; long needle-thin black bill", ["summer"]),
    "downy woodpecker": _b("na", [], "small black-and-white woodpecker; white stripe down the back; black wings with white "
                           "spots; black-and-white striped face; small red patch on the back of the head; short chisel bill"),
    "tufted titmouse": _b("na", [], "soft grey upperparts; pointed grey crest; small black patch above the bill; big black "
                          "eyes; white belly; rusty-orange flanks"),
    "dark-eyed junco": _b("na", [], "slate-grey head, back and breast; clean white belly; pale ivory bill; white outer tail "
                          "feathers; dark eyes", ["christmas"]),
    "mourning dove": _b("na", [], "soft buff-brown dove with a small round head; black spots on the wings; long pointed tail "
                        "with white tips; dark eye; reddish legs"),
    "red-winged blackbird": _b("na", [], "male glossy black all over; bright red shoulder patches edged with a yellow "
                               "stripe; pointed black bill", ["spring-easter"]),
    "great blue heron": _b("na", ["blue"], "tall blue-grey wader; white face with a black stripe above the eye ending in "
                           "black plumes; long yellow dagger bill; rusty thighs; long legs"),
    "great horned owl": _b("na", [], "large owl with tall ear tufts; mottled grey-brown body with fine bars; orange facial "
                           "disc; bright yellow eyes; white throat patch", ["halloween"]),
    "bald eagle": _b("na", [], "dark brown body and wings; bright white head and tail; big hooked yellow bill; yellow feet; "
                     "pale yellow eyes"),
    "pileated woodpecker": _b("na", [], "large black woodpecker; flaming red crest; white stripes down the face and neck; "
                              "long chisel bill; red moustache stripe"),
    "cedar waxwing": _b("na", [], "sleek soft brown-grey bird with a smooth crest; black mask edged in white; pale yellow "
                        "belly; bright yellow tail tip; small waxy red tips on the wings"),
    "northern mockingbird": _b("na", [], "slim grey bird; long dark tail with white outer feathers; white wing patches; pale "
                               "grey belly; thin dark bill; pale yellow eye"),
    "house finch": _b("na", [], "male with a bright red head, throat and breast; brown streaked back, wings and belly; short "
                      "thick grey bill"),
    # --- Svuda / omiljene ptice birdera ---
    "atlantic puffin": _b("world", ["blue"], "black back, crown and collar; white cheeks and belly; large triangular bill "
                          "striped red-orange, yellow and blue-grey; dark eye with a red eye-ring; bright orange feet"),
    "barn owl": _b("world", [], "heart-shaped white face; small black eyes; golden-buff and soft grey upperparts with tiny dark "
                   "spots; white underparts; long legs", ["halloween"]),
    "snowy owl": _b("world", [], "big white owl with black-brown spots and bars; round head; bright yellow eyes; feathered "
                    "feet", ["christmas"]),
    "crow": _b("world", [], "all glossy black body; heavy black bill; black legs; dark eye", ["halloween"]),
    "common raven": _b("world", [], "large all-black bird; shaggy throat feathers; massive black bill; wedge-shaped tail",
                       ["halloween"]),
    "rock pigeon": _b("world", ["pink", "green"], "soft grey body; iridescent green-and-violet neck; two black bars on each "
                      "wing; orange eye; red feet"),
    "barn swallow": _b("world", ["blue"], "glossy dark blue back and wings; brick-red forehead and throat; cream to rusty "
                       "belly; very long forked tail streamers; tiny bill", ["summer"]),
    "mallard": _b("world", ["green", "blue"], "male with a glossy green head; thin white neck ring; chestnut-brown breast; "
                  "pale grey body; yellow bill; orange feet; curled black tail feathers; blue wing patch edged with white"),
    "shoebill": _b("world", [], "huge slate-grey stork-like bird; giant shoe-shaped pale bill with a hooked tip; pale yellow "
                   "eyes; serious stare; long legs"),
    "flamingo": _b("world", ["pink"], "bright pink body; long thin neck and legs; bent pink bill with a black tip; black "
                   "flight feathers", ["summer"]),
}
