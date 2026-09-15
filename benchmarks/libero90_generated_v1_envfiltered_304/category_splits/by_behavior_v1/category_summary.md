# Generated Benchmark Task Categories

This file classifies the frozen generated LIBERO benchmark into behavior
buckets for scratch skill mining. It does not modify the benchmark BDDL
or the original frozen manifests.

## Overall

- Tasks: `304`
- Original splits: `{'smoke': 3, 'train': 256, 'validation': 45}`
- Templates: `{'caddy_compartment': 124, 'pick_place_on_surface': 67, 'put_inside_container': 113}`
- Derived split counts: `{'train': 227, 'test': 56, 'phase_train': 68, 'phase_test': 28}`

Runner usage: set `--generated_split all` and pass the comma-separated
`all_row_id_1based` selectors from the desired category file.

## Categories

| category | total | train | test | phase train | phase test | excluded | example |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `caddy_compartment/book` | 52 | 42 | 10 | 4 | 2 | 0 | pick up the black book and place it in the front compartment of the caddy |
| `caddy_compartment/mug` | 72 | 58 | 14 | 4 | 2 | 0 | pick up the white yellow mug and place it in the front compartment of the caddy |
| `inside/basket/can_or_bottle` | 27 | 22 | 5 | 4 | 2 | 0 | pick up the ketchup and place it in the basket |
| `inside/basket/carton_bottle` | 10 | 8 | 2 | 4 | 2 | 0 | pick up the milk and place it in the basket |
| `inside/basket/flat_box` | 14 | 11 | 3 | 4 | 2 | 0 | pick up the cream cheese and place it in the basket |
| `inside/desk_caddy/book` | 5 | 4 | 1 | 4 | 1 | 0 | pick up the black book and place it in the study table desk caddy front |
| `inside/desk_caddy/mug` | 10 | 8 | 2 | 4 | 2 | 0 | pick up the red coffee mug and place it in the study table desk caddy front |
| `inside/microwave/mug` | 4 | 0 | 0 | 0 | 0 | 4 | pick up the porcelain mug and place it in the microwave |
| `inside/microwave/white_bowl` | 3 | 0 | 0 | 0 | 0 | 3 | pick up the white bowl and place it in the microwave |
| `inside/wooden_tray/black_bowl` | 5 | 0 | 0 | 0 | 0 | 5 | pick up the akita black bowl and place it in the wooden tray |
| `inside/wooden_tray/can_or_bottle` | 15 | 12 | 3 | 4 | 2 | 0 | pick up the tomato sauce and place it in the wooden tray |
| `inside/wooden_tray/carton_bottle` | 5 | 4 | 1 | 4 | 1 | 0 | pick up the new salad dressing and place it in the wooden tray |
| `inside/wooden_tray/flat_box` | 15 | 12 | 3 | 4 | 2 | 0 | pick up the cream cheese and place it in the wooden tray |
| `surface/flat_stove/moka_pot` | 6 | 3 | 1 | 3 | 1 | 2 | pick up the moka pot and place it on the flat stove |
| `surface/flat_stove/white_bowl` | 6 | 5 | 1 | 4 | 1 | 0 | pick up the white bowl and place it on the flat stove |
| `surface/plate/black_bowl` | 17 | 8 | 2 | 4 | 2 | 7 | pick up the akita black bowl and place it on the plate |
| `surface/plate/can_or_bottle` | 5 | 4 | 1 | 4 | 1 | 0 | pick up the ketchup and place it on the plate |
| `surface/plate/flat_box` | 4 | 3 | 1 | 3 | 1 | 0 | pick up the chocolate pudding and place it on the plate |
| `surface/plate/mug` | 20 | 16 | 4 | 4 | 2 | 0 | pick up the porcelain mug and place it on the plate |
| `surface/plate/white_bowl` | 3 | 2 | 1 | 2 | 1 | 0 | pick up the white bowl and place it on the plate |
| `surface/wine_rack/black_bowl` | 6 | 5 | 1 | 4 | 1 | 0 | pick up the akita black bowl and place it on the wine rack |

## Phase-1 Train Sample

| selector | task id | category | language |
| ---: | --- | --- | --- |
| 2 | `libero_90_gen_t008_pick_place_on_surface_e57f7116` | `surface/plate/black_bowl` | pick up the akita black bowl and place it on the plate |
| 3 | `libero_90_gen_t009_pick_place_on_surface_dbdb1623` | `surface/plate/black_bowl` | pick up the akita black bowl and place it on the plate |
| 13 | `libero_90_gen_t019_pick_place_on_surface_cdc11335` | `surface/flat_stove/moka_pot` | pick up the moka pot and place it on the flat stove |
| 14 | `libero_90_gen_t020_pick_place_on_surface_d93ca791` | `surface/flat_stove/moka_pot` | pick up the moka pot and place it on the flat stove |
| 16 | `libero_90_gen_t022_pick_place_on_surface_5727e6d2` | `surface/flat_stove/moka_pot` | pick up the moka pot and place it on the flat stove |
| 18 | `libero_90_gen_t024_pick_place_on_surface_96c50975` | `surface/wine_rack/black_bowl` | pick up the akita black bowl and place it on the wine rack |
| 20 | `libero_90_gen_t026_pick_place_on_surface_47aa4131` | `surface/wine_rack/black_bowl` | pick up the akita black bowl and place it on the wine rack |
| 21 | `libero_90_gen_t027_pick_place_on_surface_50697298` | `surface/wine_rack/black_bowl` | pick up the akita black bowl and place it on the wine rack |
| 22 | `libero_90_gen_t028_pick_place_on_surface_054e21ea` | `surface/wine_rack/black_bowl` | pick up the akita black bowl and place it on the wine rack |
| 24 | `libero_90_gen_t029_pick_place_on_surface_ed9e40ac` | `surface/plate/can_or_bottle` | pick up the ketchup and place it on the plate |
| 26 | `libero_90_gen_t030_pick_place_on_surface_e0cda06e` | `surface/plate/can_or_bottle` | pick up the ketchup and place it on the plate |
| 28 | `libero_90_gen_t031_pick_place_on_surface_fd9f5ee0` | `surface/plate/can_or_bottle` | pick up the ketchup and place it on the plate |
| 29 | `libero_90_gen_t032_pick_place_on_surface_19de8342` | `surface/plate/can_or_bottle` | pick up the ketchup and place it on the plate |
| 30 | `libero_90_gen_t032_pick_place_on_surface_ddcaf567` | `surface/plate/black_bowl` | pick up the akita black bowl and place it on the plate |
| 32 | `libero_90_gen_t033_pick_place_on_surface_39e46eb3` | `surface/plate/black_bowl` | pick up the akita black bowl and place it on the plate |
| 37 | `libero_90_gen_t036_pick_place_on_surface_f31ad9b9` | `surface/plate/white_bowl` | pick up the white bowl and place it on the plate |
| 39 | `libero_90_gen_t037_pick_place_on_surface_3353a6dc` | `surface/plate/white_bowl` | pick up the white bowl and place it on the plate |
| 46 | `libero_90_gen_t042_pick_place_on_surface_5f5e31b9` | `surface/flat_stove/white_bowl` | pick up the white bowl and place it on the flat stove |
| 48 | `libero_90_gen_t044_pick_place_on_surface_3347620d` | `surface/flat_stove/white_bowl` | pick up the white bowl and place it on the flat stove |
| 49 | `libero_90_gen_t045_pick_place_on_surface_66f04a0b` | `surface/flat_stove/white_bowl` | pick up the white bowl and place it on the flat stove |
| 50 | `libero_90_gen_t046_pick_place_on_surface_fb36209e` | `surface/flat_stove/white_bowl` | pick up the white bowl and place it on the flat stove |
| 54 | `libero_90_gen_t047_put_inside_container_e811ac5b` | `inside/basket/can_or_bottle` | pick up the tomato sauce and place it in the basket |
| 56 | `libero_90_gen_t048_put_inside_container_610fab4f` | `inside/basket/can_or_bottle` | pick up the tomato sauce and place it in the basket |
| 63 | `libero_90_gen_t050_put_inside_container_7989aa4b` | `inside/basket/flat_box` | pick up the cream cheese and place it in the basket |
| 68 | `libero_90_gen_t051_put_inside_container_249cd45a` | `inside/basket/carton_bottle` | pick up the milk and place it in the basket |
| 74 | `libero_90_gen_t052_put_inside_container_0358f952` | `inside/basket/flat_box` | pick up the cream cheese and place it in the basket |
| 79 | `libero_90_gen_t052_put_inside_container_70cfb6cf` | `inside/basket/can_or_bottle` | pick up the tomato sauce and place it in the basket |
| 83 | `libero_90_gen_t053_put_inside_container_21526a83` | `inside/basket/flat_box` | pick up the cream cheese and place it in the basket |
| 88 | `libero_90_gen_t054_put_inside_container_64c81d2b` | `inside/basket/can_or_bottle` | pick up the alphabet soup and place it in the basket |
| 89 | `libero_90_gen_t054_put_inside_container_74de1f81` | `inside/basket/carton_bottle` | pick up the milk and place it in the basket |
| 95 | `libero_90_gen_t055_put_inside_container_28d7232a` | `inside/basket/carton_bottle` | pick up the milk and place it in the basket |
| 98 | `libero_90_gen_t055_put_inside_container_b01aa5ff` | `inside/basket/carton_bottle` | pick up the orange juice and place it in the basket |
| 100 | `libero_90_gen_t055_put_inside_container_e285dc25` | `inside/basket/flat_box` | pick up the cream cheese and place it in the basket |
| 105 | `libero_90_gen_t056_put_inside_container_7d6a5fb2` | `inside/wooden_tray/can_or_bottle` | pick up the ketchup and place it in the wooden tray |
| 107 | `libero_90_gen_t057_put_inside_container_2c2d2c88` | `inside/wooden_tray/flat_box` | pick up the cream cheese and place it in the wooden tray |
| 109 | `libero_90_gen_t057_put_inside_container_51e98a30` | `inside/wooden_tray/can_or_bottle` | pick up the ketchup and place it in the wooden tray |
| 113 | `libero_90_gen_t058_put_inside_container_2a4eb20c` | `inside/wooden_tray/flat_box` | pick up the cream cheese and place it in the wooden tray |
| 115 | `libero_90_gen_t058_put_inside_container_8ad72d56` | `inside/wooden_tray/can_or_bottle` | pick up the tomato sauce and place it in the wooden tray |
| 117 | `libero_90_gen_t059_put_inside_container_1d3b38b5` | `inside/wooden_tray/can_or_bottle` | pick up the tomato sauce and place it in the wooden tray |
| 127 | `libero_90_gen_t061_put_inside_container_55584e10` | `inside/wooden_tray/carton_bottle` | pick up the new salad dressing and place it in the wooden tray |
| 128 | `libero_90_gen_t061_put_inside_container_66e78aa7` | `inside/wooden_tray/flat_box` | pick up the chocolate pudding and place it in the wooden tray |
| 132 | `libero_90_gen_t062_put_inside_container_e6e4a834` | `inside/wooden_tray/carton_bottle` | pick up the new salad dressing and place it in the wooden tray |
| 135 | `libero_90_gen_t063_put_inside_container_f5b0e15b` | `inside/wooden_tray/carton_bottle` | pick up the new salad dressing and place it in the wooden tray |
| 136 | `libero_90_gen_t064_put_inside_container_4f263c65` | `inside/wooden_tray/flat_box` | pick up the chocolate pudding and place it in the wooden tray |
| 139 | `libero_90_gen_t065_put_inside_container_1336cd3c` | `inside/wooden_tray/carton_bottle` | pick up the new salad dressing and place it in the wooden tray |
| 142 | `libero_90_gen_t066_pick_place_on_surface_677bf15f` | `surface/plate/mug` | pick up the porcelain mug and place it on the plate |
| 146 | `libero_90_gen_t067_pick_place_on_surface_aca70e82` | `surface/plate/mug` | pick up the porcelain mug and place it on the plate |
| 154 | `libero_90_gen_t070_pick_place_on_surface_23c3d2cb` | `surface/plate/flat_box` | pick up the chocolate pudding and place it on the plate |
| 158 | `libero_90_gen_t071_pick_place_on_surface_926e4661` | `surface/plate/flat_box` | pick up the chocolate pudding and place it on the plate |
| 163 | `libero_90_gen_t073_pick_place_on_surface_1171afa7` | `surface/plate/mug` | pick up the red coffee mug and place it on the plate |
| 164 | `libero_90_gen_t073_pick_place_on_surface_2182e8a6` | `surface/plate/flat_box` | pick up the chocolate pudding and place it on the plate |
| 165 | `libero_90_gen_t073_pick_place_on_surface_682603bd` | `surface/plate/mug` | pick up the porcelain mug and place it on the plate |
| 189 | `libero_90_gen_t076_caddy_compartment_f40e0307` | `caddy_compartment/mug` | pick up the white yellow mug and place it in the right compartment of the caddy |
| 195 | `libero_90_gen_t077_caddy_compartment_bb340cd2` | `caddy_compartment/book` | pick up the black book and place it in the back compartment of the caddy |
| 221 | `libero_90_gen_t080_caddy_compartment_f58109d1` | `caddy_compartment/mug` | pick up the red coffee mug and place it in the front compartment of the caddy |
| 240 | `libero_90_gen_t082_caddy_compartment_c87582ff` | `caddy_compartment/book` | pick up the black book and place it in the left compartment of the caddy |
| 243 | `libero_90_gen_t082_put_inside_container_7dc83104` | `inside/desk_caddy/mug` | pick up the red coffee mug and place it in the study table desk caddy front |
| 257 | `libero_90_gen_t083_put_inside_container_2c376bf7` | `inside/desk_caddy/mug` | pick up the porcelain mug and place it in the study table desk caddy front |
| 259 | `libero_90_gen_t083_put_inside_container_cdb450d5` | `inside/desk_caddy/book` | pick up the black book and place it in the study table desk caddy front |
| 271 | `libero_90_gen_t084_caddy_compartment_dcf77fac` | `caddy_compartment/book` | pick up the black book and place it in the front compartment of the caddy |
| 274 | `libero_90_gen_t084_put_inside_container_e80ddf7f` | `inside/desk_caddy/book` | pick up the black book and place it in the study table desk caddy front |
| 284 | `libero_90_gen_t085_caddy_compartment_942293e9` | `caddy_compartment/book` | pick up the black book and place it in the back compartment of the caddy |
| 286 | `libero_90_gen_t085_caddy_compartment_c73d8831` | `caddy_compartment/mug` | pick up the porcelain mug and place it in the back compartment of the caddy |
| 288 | `libero_90_gen_t085_put_inside_container_ef3becee` | `inside/desk_caddy/book` | pick up the black book and place it in the study table desk caddy front |
| 294 | `libero_90_gen_t086_caddy_compartment_2b035e49` | `caddy_compartment/mug` | pick up the porcelain mug and place it in the front compartment of the caddy |
| 302 | `libero_90_gen_t086_put_inside_container_4cc9d0e1` | `inside/desk_caddy/mug` | pick up the porcelain mug and place it in the study table desk caddy front |
| 303 | `libero_90_gen_t086_put_inside_container_9c02bc88` | `inside/desk_caddy/book` | pick up the black book and place it in the study table desk caddy front |
| 304 | `libero_90_gen_t086_put_inside_container_eb02d587` | `inside/desk_caddy/mug` | pick up the red coffee mug and place it in the study table desk caddy front |

## Phase-1 Test Sample

| selector | task id | category | language |
| ---: | --- | --- | --- |
| 1 | `libero_90_gen_t007_pick_place_on_surface_c134fe50` | `surface/plate/black_bowl` | pick up the akita black bowl and place it on the plate |
| 15 | `libero_90_gen_t021_pick_place_on_surface_8f855ea1` | `surface/flat_stove/moka_pot` | pick up the moka pot and place it on the flat stove |
| 19 | `libero_90_gen_t025_pick_place_on_surface_9f337d0a` | `surface/wine_rack/black_bowl` | pick up the akita black bowl and place it on the wine rack |
| 23 | `libero_90_gen_t029_pick_place_on_surface_629c0b88` | `surface/plate/black_bowl` | pick up the akita black bowl and place it on the plate |
| 31 | `libero_90_gen_t033_pick_place_on_surface_159d99fc` | `surface/plate/can_or_bottle` | pick up the ketchup and place it on the plate |
| 41 | `libero_90_gen_t038_pick_place_on_surface_79948935` | `surface/plate/white_bowl` | pick up the white bowl and place it on the plate |
| 47 | `libero_90_gen_t043_pick_place_on_surface_1a4c15b2` | `surface/flat_stove/white_bowl` | pick up the white bowl and place it on the flat stove |
| 55 | `libero_90_gen_t048_put_inside_container_4d37a5f3` | `inside/basket/can_or_bottle` | pick up the ketchup and place it in the basket |
| 69 | `libero_90_gen_t051_put_inside_container_36d8dc84` | `inside/basket/flat_box` | pick up the butter and place it in the basket |
| 73 | `libero_90_gen_t051_put_inside_container_a1e5fba4` | `inside/basket/carton_bottle` | pick up the orange juice and place it in the basket |
| 75 | `libero_90_gen_t052_put_inside_container_072aab5e` | `inside/basket/can_or_bottle` | pick up the ketchup and place it in the basket |
| 80 | `libero_90_gen_t052_put_inside_container_ffa2efb8` | `inside/basket/carton_bottle` | pick up the orange juice and place it in the basket |
| 93 | `libero_90_gen_t054_put_inside_container_d9ec083b` | `inside/basket/flat_box` | pick up the butter and place it in the basket |
| 106 | `libero_90_gen_t056_put_inside_container_e2f67048` | `inside/wooden_tray/can_or_bottle` | pick up the alphabet soup and place it in the wooden tray |
| 108 | `libero_90_gen_t057_put_inside_container_2d031516` | `inside/wooden_tray/flat_box` | pick up the butter and place it in the wooden tray |
| 123 | `libero_90_gen_t060_put_inside_container_3b4fddf4` | `inside/wooden_tray/can_or_bottle` | pick up the ketchup and place it in the wooden tray |
| 125 | `libero_90_gen_t060_put_inside_container_707a21b2` | `inside/wooden_tray/flat_box` | pick up the cream cheese and place it in the wooden tray |
| 137 | `libero_90_gen_t064_put_inside_container_70c56576` | `inside/wooden_tray/carton_bottle` | pick up the new salad dressing and place it in the wooden tray |
| 157 | `libero_90_gen_t071_pick_place_on_surface_2d88520c` | `surface/plate/mug` | pick up the red coffee mug and place it on the plate |
| 161 | `libero_90_gen_t072_pick_place_on_surface_b6a96d47` | `surface/plate/flat_box` | pick up the chocolate pudding and place it on the plate |
| 162 | `libero_90_gen_t072_pick_place_on_surface_e808fe38` | `surface/plate/mug` | pick up the red coffee mug and place it on the plate |
| 178 | `libero_90_gen_t075_caddy_compartment_627dc685` | `caddy_compartment/book` | pick up the black book and place it in the right compartment of the caddy |
| 193 | `libero_90_gen_t077_caddy_compartment_7694d452` | `caddy_compartment/book` | pick up the black book and place it in the right compartment of the caddy |
| 194 | `libero_90_gen_t077_caddy_compartment_91a1b0df` | `caddy_compartment/mug` | pick up the white yellow mug and place it in the left compartment of the caddy |
| 242 | `libero_90_gen_t082_put_inside_container_396769b3` | `inside/desk_caddy/book` | pick up the black book and place it in the study table desk caddy front |
| 258 | `libero_90_gen_t083_put_inside_container_852a841b` | `inside/desk_caddy/mug` | pick up the red coffee mug and place it in the study table desk caddy front |
| 273 | `libero_90_gen_t084_put_inside_container_e35e2e18` | `inside/desk_caddy/mug` | pick up the red coffee mug and place it in the study table desk caddy front |
| 301 | `libero_90_gen_t086_caddy_compartment_f1c10f48` | `caddy_compartment/mug` | pick up the red coffee mug and place it in the left compartment of the caddy |
