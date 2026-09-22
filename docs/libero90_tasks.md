# LIBERO-90 task list (90 tasks)

Source: the frozen inventory in this repo, `benchmarks/libero90_generated_v1_envfiltered_304/inventory/libero_90_tasks.jsonl`
(generated from the installed LIBERO package in the evaluation environment; task order follows
the benchmark's canonical order).

| # | instruction | objects of interest | bddl file |
| ---: | --- | --- | --- |
| 1 | close the top drawer of the cabinet | `wooden_cabinet_1` | `KITCHEN_SCENE10_close_the_top_drawer_of_the_cabinet.bddl` |
| 2 | close the top drawer of the cabinet and put the black bowl on top of it | `wooden_cabinet_1`, `akita_black_bowl_1` | `KITCHEN_SCENE10_close_the_top_drawer_of_the_cabinet_and_put_the_black_bowl_on_top_of_it.bddl` |
| 3 | put the black bowl in the top drawer of the cabinet | `akita_black_bowl_1`, `wooden_cabinet_1` | `KITCHEN_SCENE10_put_the_black_bowl_in_the_top_drawer_of_the_cabinet.bddl` |
| 4 | put the butter at the back in the top drawer of the cabinet and close it | `butter_2`, `wooden_cabinet_1` | `KITCHEN_SCENE10_put_the_butter_at_the_back_in_the_top_drawer_of_the_cabinet_and_close_it.bddl` |
| 5 | put the butter at the front in the top drawer of the cabinet and close it | `butter_1`, `wooden_cabinet_1` | `KITCHEN_SCENE10_put_the_butter_at_the_front_in_the_top_drawer_of_the_cabinet_and_close_it.bddl` |
| 6 | put the chocolate pudding in the top drawer of the cabinet and close it | `chocolate_pudding_1`, `wooden_cabinet_1` | `KITCHEN_SCENE10_put_the_chocolate_pudding_in_the_top_drawer_of_the_cabinet_and_close_it.bddl` |
| 7 | open the bottom drawer of the cabinet | `wooden_cabinet_1` | `KITCHEN_SCENE1_open_the_bottom_drawer_of_the_cabinet.bddl` |
| 8 | open the top drawer of the cabinet | `wooden_cabinet_1` | `KITCHEN_SCENE1_open_the_top_drawer_of_the_cabinet.bddl` |
| 9 | open the top drawer of the cabinet and put the bowl in it | `wooden_cabinet_1`, `akita_black_bowl_1` | `KITCHEN_SCENE1_open_the_top_drawer_of_the_cabinet_and_put_the_bowl_in_it.bddl` |
| 10 | put the black bowl on the plate | `akita_black_bowl_1`, `plate_1` | `KITCHEN_SCENE1_put_the_black_bowl_on_the_plate.bddl` |
| 11 | put the black bowl on top of the cabinet | `akita_black_bowl_1`, `wooden_cabinet_1` | `KITCHEN_SCENE1_put_the_black_bowl_on_top_of_the_cabinet.bddl` |
| 12 | open the top drawer of the cabinet | `wooden_cabinet_1` | `KITCHEN_SCENE2_open_the_top_drawer_of_the_cabinet.bddl` |
| 13 | put the black bowl at the back on the plate | `akita_black_bowl_3`, `plate_1` | `KITCHEN_SCENE2_put_the_black_bowl_at_the_back_on_the_plate.bddl` |
| 14 | put the black bowl at the front on the plate | `akita_black_bowl_1`, `plate_1` | `KITCHEN_SCENE2_put_the_black_bowl_at_the_front_on_the_plate.bddl` |
| 15 | put the middle black bowl on the plate | `akita_black_bowl_2`, `plate_1` | `KITCHEN_SCENE2_put_the_middle_black_bowl_on_the_plate.bddl` |
| 16 | put the middle black bowl on top of the cabinet | `akita_black_bowl_2`, `wooden_cabinet_1` | `KITCHEN_SCENE2_put_the_middle_black_bowl_on_top_of_the_cabinet.bddl` |
| 17 | stack the black bowl at the front on the black bowl in the middle | `akita_black_bowl_1`, `akita_black_bowl_2` | `KITCHEN_SCENE2_stack_the_black_bowl_at_the_front_on_the_black_bowl_in_the_middle.bddl` |
| 18 | stack the middle black bowl on the back black bowl | `akita_black_bowl_2`, `akita_black_bowl_3` | `KITCHEN_SCENE2_stack_the_middle_black_bowl_on_the_back_black_bowl.bddl` |
| 19 | put the frying pan on the stove | `chefmate_8_frypan_1`, `flat_stove_1` | `KITCHEN_SCENE3_put_the_frying_pan_on_the_stove.bddl` |
| 20 | put the moka pot on the stove | `moka_pot_1`, `flat_stove_1` | `KITCHEN_SCENE3_put_the_moka_pot_on_the_stove.bddl` |
| 21 | turn on the stove | `flat_stove_1` | `KITCHEN_SCENE3_turn_on_the_stove.bddl` |
| 22 | turn on the stove and put the frying pan on it | `chefmate_8_frypan_1`, `flat_stove_1` | `KITCHEN_SCENE3_turn_on_the_stove_and_put_the_frying_pan_on_it.bddl` |
| 23 | close the bottom drawer of the cabinet | `white_cabinet_1` | `KITCHEN_SCENE4_close_the_bottom_drawer_of_the_cabinet.bddl` |
| 24 | close the bottom drawer of the cabinet and open the top drawer | `white_cabinet_1` | `KITCHEN_SCENE4_close_the_bottom_drawer_of_the_cabinet_and_open_the_top_drawer.bddl` |
| 25 | put the black bowl in the bottom drawer of the cabinet | `akita_black_bowl_1`, `white_cabinet_1` | `KITCHEN_SCENE4_put_the_black_bowl_in_the_bottom_drawer_of_the_cabinet.bddl` |
| 26 | put the black bowl on top of the cabinet | `akita_black_bowl_1`, `white_cabinet_1` | `KITCHEN_SCENE4_put_the_black_bowl_on_top_of_the_cabinet.bddl` |
| 27 | put the wine bottle in the bottom drawer of the cabinet | `wine_bottle_1`, `white_cabinet_1` | `KITCHEN_SCENE4_put_the_wine_bottle_in_the_bottom_drawer_of_the_cabinet.bddl` |
| 28 | put the wine bottle on the wine rack | `wine_bottle_1`, `wine_rack_1` | `KITCHEN_SCENE4_put_the_wine_bottle_on_the_wine_rack.bddl` |
| 29 | close the top drawer of the cabinet | `white_cabinet_1` | `KITCHEN_SCENE5_close_the_top_drawer_of_the_cabinet.bddl` |
| 30 | put the black bowl in the top drawer of the cabinet | `akita_black_bowl_1`, `white_cabinet_1` | `KITCHEN_SCENE5_put_the_black_bowl_in_the_top_drawer_of_the_cabinet.bddl` |
| 31 | put the black bowl on the plate | `akita_black_bowl_1`, `plate_1` | `KITCHEN_SCENE5_put_the_black_bowl_on_the_plate.bddl` |
| 32 | put the black bowl on top of the cabinet | `akita_black_bowl_1`, `white_cabinet_1` | `KITCHEN_SCENE5_put_the_black_bowl_on_top_of_the_cabinet.bddl` |
| 33 | put the ketchup in the top drawer of the cabinet | `ketchup_1`, `white_cabinet_1` | `KITCHEN_SCENE5_put_the_ketchup_in_the_top_drawer_of_the_cabinet.bddl` |
| 34 | close the microwave | `microwave_1` | `KITCHEN_SCENE6_close_the_microwave.bddl` |
| 35 | put the yellow and white mug to the front of the white mug | `porcelain_mug_1`, `white_yellow_mug_1` | `KITCHEN_SCENE6_put_the_yellow_and_white_mug_to_the_front_of_the_white_mug.bddl` |
| 36 | open the microwave | `microwave_1` | `KITCHEN_SCENE7_open_the_microwave.bddl` |
| 37 | put the white bowl on the plate | `white_bowl_1`, `plate_1` | `KITCHEN_SCENE7_put_the_white_bowl_on_the_plate.bddl` |
| 38 | put the white bowl to the right of the plate | `white_bowl_1`, `plate_1` | `KITCHEN_SCENE7_put_the_white_bowl_to_the_right_of_the_plate.bddl` |
| 39 | put the right moka pot on the stove | `moka_pot_1`, `flat_stove_1` | `KITCHEN_SCENE8_put_the_right_moka_pot_on_the_stove.bddl` |
| 40 | turn off the stove | `flat_stove_1` | `KITCHEN_SCENE8_turn_off_the_stove.bddl` |
| 41 | put the frying pan on the cabinet shelf | `chefmate_8_frypan_1`, `wooden_two_layer_shelf_1` | `KITCHEN_SCENE9_put_the_frying_pan_on_the_cabinet_shelf.bddl` |
| 42 | put the frying pan on top of the cabinet | `chefmate_8_frypan_1`, `wooden_two_layer_shelf_1` | `KITCHEN_SCENE9_put_the_frying_pan_on_top_of_the_cabinet.bddl` |
| 43 | put the frying pan under the cabinet shelf | `chefmate_8_frypan_1`, `wooden_two_layer_shelf_1` | `KITCHEN_SCENE9_put_the_frying_pan_under_the_cabinet_shelf.bddl` |
| 44 | put the white bowl on top of the cabinet | `white_bowl_1`, `wooden_two_layer_shelf_1` | `KITCHEN_SCENE9_put_the_white_bowl_on_top_of_the_cabinet.bddl` |
| 45 | turn on the stove | `flat_stove_1` | `KITCHEN_SCENE9_turn_on_the_stove.bddl` |
| 46 | turn on the stove and put the frying pan on it | `flat_stove_1`, `chefmate_8_frypan_1` | `KITCHEN_SCENE9_turn_on_the_stove_and_put_the_frying_pan_on_it.bddl` |
| 47 | pick up the alphabet soup and put it in the basket | `alphabet_soup_1`, `basket_1` | `LIVING_ROOM_SCENE1_pick_up_the_alphabet_soup_and_put_it_in_the_basket.bddl` |
| 48 | pick up the cream cheese box and put it in the basket | `cream_cheese_1`, `basket_1` | `LIVING_ROOM_SCENE1_pick_up_the_cream_cheese_box_and_put_it_in_the_basket.bddl` |
| 49 | pick up the ketchup and put it in the basket | `ketchup_1`, `basket_1` | `LIVING_ROOM_SCENE1_pick_up_the_ketchup_and_put_it_in_the_basket.bddl` |
| 50 | pick up the tomato sauce and put it in the basket | `tomato_sauce_1`, `basket_1` | `LIVING_ROOM_SCENE1_pick_up_the_tomato_sauce_and_put_it_in_the_basket.bddl` |
| 51 | pick up the alphabet soup and put it in the basket | `alphabet_soup_1`, `basket_1` | `LIVING_ROOM_SCENE2_pick_up_the_alphabet_soup_and_put_it_in_the_basket.bddl` |
| 52 | pick up the butter and put it in the basket | `butter_1`, `basket_1` | `LIVING_ROOM_SCENE2_pick_up_the_butter_and_put_it_in_the_basket.bddl` |
| 53 | pick up the milk and put it in the basket | `milk_1`, `basket_1` | `LIVING_ROOM_SCENE2_pick_up_the_milk_and_put_it_in_the_basket.bddl` |
| 54 | pick up the orange juice and put it in the basket | `orange_juice_1`, `basket_1` | `LIVING_ROOM_SCENE2_pick_up_the_orange_juice_and_put_it_in_the_basket.bddl` |
| 55 | pick up the tomato sauce and put it in the basket | `tomato_sauce_1`, `basket_1` | `LIVING_ROOM_SCENE2_pick_up_the_tomato_sauce_and_put_it_in_the_basket.bddl` |
| 56 | pick up the alphabet soup and put it in the tray | `alphabet_soup_1`, `wooden_tray_1` | `LIVING_ROOM_SCENE3_pick_up_the_alphabet_soup_and_put_it_in_the_tray.bddl` |
| 57 | pick up the butter and put it in the tray | `butter_1`, `wooden_tray_1` | `LIVING_ROOM_SCENE3_pick_up_the_butter_and_put_it_in_the_tray.bddl` |
| 58 | pick up the cream cheese and put it in the tray | `cream_cheese_1`, `wooden_tray_1` | `LIVING_ROOM_SCENE3_pick_up_the_cream_cheese_and_put_it_in_the_tray.bddl` |
| 59 | pick up the ketchup and put it in the tray | `ketchup_1`, `wooden_tray_1` | `LIVING_ROOM_SCENE3_pick_up_the_ketchup_and_put_it_in_the_tray.bddl` |
| 60 | pick up the tomato sauce and put it in the tray | `tomato_sauce_1`, `wooden_tray_1` | `LIVING_ROOM_SCENE3_pick_up_the_tomato_sauce_and_put_it_in_the_tray.bddl` |
| 61 | pick up the black bowl on the left and put it in the tray | `akita_black_bowl_1`, `wooden_tray_1` | `LIVING_ROOM_SCENE4_pick_up_the_black_bowl_on_the_left_and_put_it_in_the_tray.bddl` |
| 62 | pick up the chocolate pudding and put it in the tray | `chocolate_pudding_1`, `wooden_tray_1` | `LIVING_ROOM_SCENE4_pick_up_the_chocolate_pudding_and_put_it_in_the_tray.bddl` |
| 63 | pick up the salad dressing and put it in the tray | `new_salad_dressing_1`, `wooden_tray_1` | `LIVING_ROOM_SCENE4_pick_up_the_salad_dressing_and_put_it_in_the_tray.bddl` |
| 64 | stack the left bowl on the right bowl and place them in the tray | `akita_black_bowl_1`, `akita_black_bowl_2`, `wooden_tray_1` | `LIVING_ROOM_SCENE4_stack_the_left_bowl_on_the_right_bowl_and_place_them_in_the_tray.bddl` |
| 65 | stack the right bowl on the left bowl and place them in the tray | `akita_black_bowl_1`, `akita_black_bowl_2`, `wooden_tray_1` | `LIVING_ROOM_SCENE4_stack_the_right_bowl_on_the_left_bowl_and_place_them_in_the_tray.bddl` |
| 66 | put the red mug on the left plate | `red_coffee_mug_1`, `plate_1` | `LIVING_ROOM_SCENE5_put_the_red_mug_on_the_left_plate.bddl` |
| 67 | put the red mug on the right plate | `red_coffee_mug_1`, `plate_2` | `LIVING_ROOM_SCENE5_put_the_red_mug_on_the_right_plate.bddl` |
| 68 | put the white mug on the left plate | `porcelain_mug_1`, `plate_1` | `LIVING_ROOM_SCENE5_put_the_white_mug_on_the_left_plate.bddl` |
| 69 | put the yellow and white mug on the right plate | `white_yellow_mug_1`, `plate_2` | `LIVING_ROOM_SCENE5_put_the_yellow_and_white_mug_on_the_right_plate.bddl` |
| 70 | put the chocolate pudding to the left of the plate | `chocolate_pudding_1`, `plate_1` | `LIVING_ROOM_SCENE6_put_the_chocolate_pudding_to_the_left_of_the_plate.bddl` |
| 71 | put the chocolate pudding to the right of the plate | `chocolate_pudding_1`, `plate_1` | `LIVING_ROOM_SCENE6_put_the_chocolate_pudding_to_the_right_of_the_plate.bddl` |
| 72 | put the red mug on the plate | `red_coffee_mug_1`, `plate_1` | `LIVING_ROOM_SCENE6_put_the_red_mug_on_the_plate.bddl` |
| 73 | put the white mug on the plate | `porcelain_mug_1`, `plate_1` | `LIVING_ROOM_SCENE6_put_the_white_mug_on_the_plate.bddl` |
| 74 | pick up the book and place it in the front compartment of the caddy | `black_book_1`, `desk_caddy_1` | `STUDY_SCENE1_pick_up_the_book_and_place_it_in_the_front_compartment_of_the_caddy.bddl` |
| 75 | pick up the book and place it in the left compartment of the caddy | `black_book_1`, `desk_caddy_1` | `STUDY_SCENE1_pick_up_the_book_and_place_it_in_the_left_compartment_of_the_caddy.bddl` |
| 76 | pick up the book and place it in the right compartment of the caddy | `black_book_1`, `desk_caddy_1` | `STUDY_SCENE1_pick_up_the_book_and_place_it_in_the_right_compartment_of_the_caddy.bddl` |
| 77 | pick up the yellow and white mug and place it to the right of the caddy | `white_yellow_mug_1`, `desk_caddy_1` | `STUDY_SCENE1_pick_up_the_yellow_and_white_mug_and_place_it_to_the_right_of_the_caddy.bddl` |
| 78 | pick up the book and place it in the back compartment of the caddy | `black_book_1`, `desk_caddy_1` | `STUDY_SCENE2_pick_up_the_book_and_place_it_in_the_back_compartment_of_the_caddy.bddl` |
| 79 | pick up the book and place it in the front compartment of the caddy | `black_book_1`, `desk_caddy_1` | `STUDY_SCENE2_pick_up_the_book_and_place_it_in_the_front_compartment_of_the_caddy.bddl` |
| 80 | pick up the book and place it in the left compartment of the caddy | `black_book_1`, `desk_caddy_1` | `STUDY_SCENE2_pick_up_the_book_and_place_it_in_the_left_compartment_of_the_caddy.bddl` |
| 81 | pick up the book and place it in the right compartment of the caddy | `black_book_1`, `desk_caddy_1` | `STUDY_SCENE2_pick_up_the_book_and_place_it_in_the_right_compartment_of_the_caddy.bddl` |
| 82 | pick up the book and place it in the front compartment of the caddy | `black_book_1`, `desk_caddy_1` | `STUDY_SCENE3_pick_up_the_book_and_place_it_in_the_front_compartment_of_the_caddy.bddl` |
| 83 | pick up the book and place it in the left compartment of the caddy | `black_book_1`, `desk_caddy_1` | `STUDY_SCENE3_pick_up_the_book_and_place_it_in_the_left_compartment_of_the_caddy.bddl` |
| 84 | pick up the book and place it in the right compartment of the caddy | `black_book_1`, `desk_caddy_1` | `STUDY_SCENE3_pick_up_the_book_and_place_it_in_the_right_compartment_of_the_caddy.bddl` |
| 85 | pick up the red mug and place it to the right of the caddy | `red_coffee_mug_1`, `desk_caddy_1` | `STUDY_SCENE3_pick_up_the_red_mug_and_place_it_to_the_right_of_the_caddy.bddl` |
| 86 | pick up the white mug and place it to the right of the caddy | `porcelain_mug_1`, `desk_caddy_1` | `STUDY_SCENE3_pick_up_the_white_mug_and_place_it_to_the_right_of_the_caddy.bddl` |
| 87 | pick up the book in the middle and place it on the cabinet shelf | `black_book_1`, `wooden_two_layer_shelf_1` | `STUDY_SCENE4_pick_up_the_book_in_the_middle_and_place_it_on_the_cabinet_shelf.bddl` |
| 88 | pick up the book on the left and place it on top of the shelf | `yellow_book_2`, `wooden_two_layer_shelf_1` | `STUDY_SCENE4_pick_up_the_book_on_the_left_and_place_it_on_top_of_the_shelf.bddl` |
| 89 | pick up the book on the right and place it on the cabinet shelf | `yellow_book_1`, `wooden_two_layer_shelf_1` | `STUDY_SCENE4_pick_up_the_book_on_the_right_and_place_it_on_the_cabinet_shelf.bddl` |
| 90 | pick up the book on the right and place it under the cabinet shelf | `yellow_book_1`, `wooden_two_layer_shelf_1` | `STUDY_SCENE4_pick_up_the_book_on_the_right_and_place_it_under_the_cabinet_shelf.bddl` |

## Notes

- 90 rows; 74 unique instruction strings (some scenes repeat an instruction across variants).
- Scenes: KITCHEN (tasks 1-46), LIVING (47-73), STUDY (74-90).
- Tasks 47-55 mirror the object-axis basket tasks; 56-63 are tray variants; 74-90 are the
  book/mug/caddy study tasks.
