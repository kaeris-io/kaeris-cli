items = { $gender ->
        [male] { $count ->
            [one] { $count } item
           *[other] { $count } items
        }
       *[other] { $count ->
            [one] { $count } item
           *[other] { $count } items
        }
    }
