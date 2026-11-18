items = { $gender ->
        [male] { $count ->
            [one] { $count } przedmiot
           *[other] { $count } przedmiotu
        }
       *[other] { $count ->
            [one] { $count } przedmiot
           *[other] { $count } przedmiotu
        }
    }
