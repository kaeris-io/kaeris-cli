items = { $gender ->
        [male] { $count ->
            [one] { $count } przedmiot
            [few] { $count } przedmioty
            [many] { $count } przedmiotów
           *[other] { $count } przedmiotu
        }
       *[other] { $count ->
            [one] { $count } przedmiot
            [few] { $count } przedmioty
            [many] { $count } przedmiotów
           *[other] { $count } przedmiotu
        }
    }
