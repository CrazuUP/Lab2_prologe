% Minecraft

% Блоки, существующие в игре (block)
block(stone).
block(iron_ore).
block(diamond_ore).
block(oak_log).
block(obsidian).
block(quartz_ore).
block(end_stone).

% Предметы, существующие в игре (item)
item(iron_ingot).
item(diamond).
item(stick).
item(wooden_pickaxe).
item(iron_pickaxe).
item(diamond_pickaxe).
item(bread).
item(rotten_flesh).
item(raw_beef).
item(bone).
item(wool).

% Инструменты - подмножество предметов (tool)
tool(wooden_pickaxe).
tool(iron_pickaxe).
tool(diamond_pickaxe).

% Съедобные предметы (edible)
edible(bread).
edible(rotten_flesh).
edible(raw_beef).

% Все мобы (mob)
mob(zombie).
mob(skeleton).
mob(creeper).
mob(cow).
mob(sheep).

% Враждебные мобы (hostile_mob)
hostile_mob(zombie).
hostile_mob(skeleton).
hostile_mob(creeper).

% Мирные мобы (passive_mob)
passive_mob(cow).
passive_mob(sheep).

% Измерения (миры) игры (dimension)
dimension(overworld).
dimension(nether).
dimension(end).

% drops(Моб, Предмет) - какой предмет выпадает с моба
drops(zombie, rotten_flesh).
drops(skeleton, bone).
drops(cow, raw_beef).
drops(sheep, wool).

% found_in(Блок, Измерение) - в каком измерении встречается блок
found_in(iron_ore, overworld).
found_in(diamond_ore, overworld).
found_in(obsidian, overworld).
found_in(quartz_ore, nether).
found_in(end_stone, end).

% required_tool(Блок, Инструмент) - инструмент, необходимый для добычи блока
required_tool(diamond_ore, iron_pickaxe).
required_tool(obsidian, diamond_pickaxe).

% craft_ingredient(Предмет, Ингредиент) - ингредиент, нужный для крафта предмета
craft_ingredient(iron_pickaxe, iron_ingot).
craft_ingredient(iron_pickaxe, stick).
craft_ingredient(diamond_pickaxe, diamond).
craft_ingredient(diamond_pickaxe, stick).


/*ПРАВИЛА*/

% Правило 1: безопасный лут.
% Предмет выпадает с мирного моба.
farmable_drop(Mob, Drop) :-
    passive_mob(Mob),
    drops(Mob, Drop).

% Правило 2: опасный лут.
% Предмет выпадает с враждебного моба, то есть нужно сражаться.
dangerous_drop(Mob, Drop) :-
    hostile_mob(Mob),
    drops(Mob, Drop).

% Правило 3: возможность добыть блок инструментом.
% Вариант 1: инструмент прямо указан как требуемый для этого блока.
can_mine(Tool, Block) :-
    block(Block),
    required_tool(Block, Tool).
% Вариант 2: для блока специальный инструмент не нужен (отрицание),
% тогда подойдёт любой инструмент.
can_mine(Tool, Block) :-
    block(Block),
    tool(Tool),
    \+ required_tool(Block, _).

% Правило 4: безопасная еда.
% Съедобный предмет, который не выпадает с враждебных мобов
% (хлеб тоже подходит: он ни с кого не выпадает, его крафтят).
safe_food(Item) :-
    edible(Item),
    \+ (drops(Mob, Item), hostile_mob(Mob)).

% Правило 5: ценный ресурс измерения.
% Блок, найденный в измерении, для добычи которого нужен особый инструмент.
valuable_resource(Dimension, Block) :-
    found_in(Block, Dimension),
    required_tool(Block, _).

% Правило 6: объект требует исследования Незера (Нижнего мира).
needs_nether_exploration(Object) :-
    found_in(Object, nether).










