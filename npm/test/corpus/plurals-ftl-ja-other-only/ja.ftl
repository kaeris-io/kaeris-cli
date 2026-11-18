items = { $gender ->
        [male] { $count ->
           *[other] { $count }個のアイテム
        }
       *[other] { $count ->
           *[other] { $count }個のアイテム
        }
    }
